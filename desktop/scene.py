"""Project and paint the shared study from each fixed camera."""
from collections import OrderedDict
import hashlib
import heapq
import json
import math
from pathlib import Path
import random
from time import monotonic

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QImageReader, QPainter, QPainterPath,
                          QPen, QPixmap, QPolygonF, QRadialGradient, QTransform)
from PySide6.QtWidgets import QWidget

from .book_painting import draw_book
from .study_geometry import (CAMERAS, LANDMARKS, SHELF_BOARD_BASES,
                             SHELF_BOARD_THICKNESS, WINDOW,
                             book_volume, dot, sub)


INK = '#776f62'
PAPER = '#eeeae1'


class RoomScene(QWidget):
    action_requested = Signal(str)

    def __init__(self, image_path=None, parent=None):
        super().__init__(parent)
        self.assets_root = Path(image_path).parent if image_path else Path('.')
        self.data_root = None
        self.books = []
        self.book_hits = []
        self.hotspot_hits = []
        self.ui_exclusions = []
        self.furniture_hits = []  # Kept empty: furnishings are part of the set.
        self.configuration_mode = False
        self.selected_slot_id = None
        self.immersive = False
        self.outdoor = False
        self.hotspots_visible = True
        self.hovered = None
        self.motion = True
        self.phase = 0.0
        self.night_mode = False
        self.music_playing = False
        self.record_angle = 0.0
        self._clock = monotonic
        self._last_frame_time = self._clock()
        self._elapsed = 0.0
        self._visual_signature = None
        self._visual_revision = 0
        self._scene_cache = OrderedDict()
        self._cache_limit = 6
        self.static_build_count = 0
        self._projection_stamp = None
        self._projection = None
        self._view_offset = 0.0
        self._night_texture_cache = {}
        self.current_view = 'room'
        self._suppress_left_release = False
        self._book_image_cache = {}
        self._book_texture_cache = {}
        self._landscapes = {}
        self._detail_texture_cache = {}
        self.setMouseTracking(True)
        self.animation = QTimer(self)
        self.animation.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation.setInterval(16)
        self.animation.timeout.connect(self.advance)
        self.animation.start()

    @property
    def current_camera(self):
        return CAMERAS['outside' if self.outdoor else self.current_view]

    def set_view(self, page):
        if page not in CAMERAS or page == 'outside':
            raise ValueError('Unknown study view.')
        self.current_view = page
        self.book_hits = []
        self.hotspot_hits = []
        self.hovered = None
        self.setToolTip('')
        self.update()

    def set_view_offset(self, x):
        """Shift drawing and hit areas together to leave room for the page panel."""
        value = float(x)
        if not math.isfinite(value):
            raise ValueError('The scene offset must be a finite number.')
        if value != self._view_offset:
            self._view_offset = value
            self.book_hits = []
            self.hotspot_hits = []
            self.hovered = None
            self.setToolTip('')
            self.update()

    def configure(self, home, projects):
        projects = list(projects)
        signature = tuple((book['id'], book.get('title'), book.get('color'),
                           book.get('book_slot'), book.get('book_facing'),
                           json.dumps(book.get('book_appearance', {}), sort_keys=True))
                          for book in projects)
        self.books = projects
        if signature != self._visual_signature:
            self._visual_signature = signature
            self._visual_revision += 1
            self._scene_cache.clear()
            self._book_texture_cache.clear()
            self._night_texture_cache.clear()
            self.book_hits = []
            self.update()

    def advance(self):
        now = self._clock()
        elapsed = max(0.0, min(now - self._last_frame_time, .1))
        self._last_frame_time = now
        if not self.motion:
            return
        self._elapsed += elapsed
        self.phase = self._elapsed * 10
        if self.music_playing:
            # At 33 1/3 rpm the record turns 200 degrees per elapsed second.
            self.record_angle = (self.record_angle + 200 * elapsed) % 360
        if self.isVisible() and not self.outdoor:
            self.update()

    def set_motion(self, enabled):
        self.motion = bool(enabled)
        self._last_frame_time = self._clock()
        self.animation.start() if self.motion and self.isVisible() else self.animation.stop()
        self.update()

    def set_music_playing(self, playing):
        playing = bool(playing)
        if playing != self.music_playing:
            self.music_playing = playing
            self._last_frame_time = self._clock()
            self.update()

    def set_night_mode(self, enabled):
        enabled = bool(enabled)
        if enabled != self.night_mode:
            self.night_mode = enabled
            self.hovered = None
            self.update()

    def _projection_values(self):
        camera = self.current_camera
        stamp = (camera, self.width(), self.height(), self._view_offset)
        if stamp != self._projection_stamp:
            right, up, forward = camera.basis
            scale = camera.scale * min(self.width()/1440, self.height()/900)
            self._projection = (camera, right, up, forward, scale,
                                self.width()*camera.anchor[0] + self._view_offset,
                                self.height()*camera.anchor[1])
            self._projection_stamp = stamp
        return self._projection

    def project_world(self, point):
        camera, right, up, forward, scale, x, y = self._projection_values()
        relative = sub(point, camera.target)
        return QPointF(x + dot(relative, right)*scale, y - dot(relative, up)*scale)

    def _depth(self, points):
        average = tuple(sum(point[n] for point in points)/len(points) for n in range(3))
        camera, right, up, forward, scale, x, y = self._projection_values()
        return dot(sub(average, camera.eye), forward)

    def _color(self, value):
        color = QColor(value)
        if self.night_mode:
            # Shift materials towards the night palette; add lamplight separately.
            color = QColor(round(color.red()*.32+12), round(color.green()*.36+20),
                           round(color.blue()*.43+37), color.alpha())
        return color

    def _night_texture(self, image):
        if not self.night_mode:
            return image
        key = image.cacheKey()
        if key not in self._night_texture_cache:
            shaded = QPixmap(image)
            painter = QPainter(shaded)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            painter.fillRect(shaded.rect(), QColor(18, 30, 51, 132))
            painter.end()
            self._night_texture_cache[key] = shaded
        return self._night_texture_cache[key]

    def _face(self, points, color, grain=False, image=None, book=None):
        self.faces.append((self._depth(points), points, color, grain, image, book))

    def _line(self, p, points, color=INK, width=.8):
        p.setPen(QPen(self._color(color), width, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolyline(QPolygonF([self.project_world(v) for v in points]))

    def _polygon(self, p, points, color, stroke=True):
        polygon = QPolygonF([self.project_world(v) for v in points])
        p.setBrush(self._color(color))
        p.setPen(QPen(self._color(INK), .55, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin) if stroke else Qt.PenStyle.NoPen)
        p.drawPolygon(polygon)
        if stroke:
            # Offset a second outline to give edges a pencil texture.
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(147, 161, 179, 35) if self.night_mode else QColor(96, 88, 71, 46), .45))
            for n in range(len(polygon)):
                a, b = polygon[n], polygon[(n+1) % len(polygon)]
                path = QPainterPath(a)
                bend = math.sin(a.x()*.07 + a.y()*.05) * .85
                middle = (a+b)*.5 + QPointF(bend, -bend*.55)
                path.quadTo(middle, b)
                p.drawPath(path)
        return polygon

    def _box(self, x, y, z, w, d, h, color, wood=False):
        c = QColor(color)
        a=(x,y,z); b=(x+w,y,z); c0=(x+w,y+d,z); d0=(x,y+d,z)
        A=(x,y,z+h); B=(x+w,y,z+h); C=(x+w,y+d,z+h); D=(x,y+d,z+h)
        eye = self.current_camera.eye
        if eye[1] < y+d/2:
            self._face([A,B,b,a], c.darker(106).name(), wood)
        else:
            self._face([C,D,d0,c0], c.darker(118).name(), wood)
        if eye[0] > x+w/2:
            self._face([B,C,c0,b], c.darker(118).name(), wood)
        else:
            self._face([D,A,a,d0], c.darker(110).name(), wood)
        self._face([D,C,B,A], c.lighter(108).name(), wood)

    def _cylinder(self, x,y,z,r,h,color,top_r=None):
        top_r = r if top_r is None else top_r
        sides=20
        c=QColor(color)
        lower=[(x+math.cos(n*2*math.pi/sides)*r,y+math.sin(n*2*math.pi/sides)*r,z) for n in range(sides)]
        upper=[(x+math.cos(n*2*math.pi/sides)*top_r,y+math.sin(n*2*math.pi/sides)*top_r,z+h) for n in range(sides)]
        for n in range(sides):
            m=(n+1)%sides
            shade=100+int(13*(1+math.cos(n*2*math.pi/sides))/2)
            self._face([upper[n],upper[m],lower[m],lower[n]],c.darker(shade).name(),'ceramic')
        self._face(list(reversed(upper)),c.lighter(107).name(),'ceramic')

    def _ellipse(self,p,x,y,z,rx,ry,color):
        points=[(x+math.cos(n*math.pi/30)*rx,y+math.sin(n*math.pi/30)*ry,z) for n in range(60)]
        self._polygon(p,points,color,False)

    def _shadow(self,p,x,y,rx,ry):
        for n in range(8,0,-1):
            color=QColor('#6b6656'); color.setAlpha(3+(8-n))
            self._ellipse(p,x+.04,y+.04,.012,rx*(1+n*.055),ry*(1+n*.055),color)

    def _map_image(self,p,image,points,night_shade=True):
        if night_shade:
            image = self._night_texture(image)
        a,b,c,d=[self.project_world(v) for v in points]
        transform=QTransform((b.x()-a.x())/image.width(),(b.y()-a.y())/image.width(),
                             (d.x()-a.x())/image.height(),(d.y()-a.y())/image.height(),a.x(),a.y())
        p.save(); p.setTransform(transform,True)
        p.drawPixmap(0,0,image)
        p.restore()

    def _fabric_texture(self,key,color,w,h):
        if key in self._detail_texture_cache:return self._detail_texture_cache[key]
        image=QPixmap(w,h);image.fill(Qt.GlobalColor.transparent)
        p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline=QColor(color).darker(117)
        p.setPen(QPen(outline,2));p.setBrush(QColor(color))
        path=QPainterPath(QPointF(28,9))
        path.cubicTo(w*.35,1,w*.70,3,w-23,11)
        path.cubicTo(w+2,h*.25,w-3,h*.76,w-18,h-15)
        path.cubicTo(w*.74,h+1,w*.27,h-2,18,h-12)
        path.cubicTo(0,h*.72,2,h*.27,11,24)
        path.quadTo(16,12,28,9);path.closeSubpath()
        p.drawPath(path);p.setClipPath(path)
        rng=random.Random(91)
        for n in range(900):
            x,y=rng.randrange(w),rng.randrange(h)
            p.setPen(QPen(QColor(66,76,56,15),.7));p.drawLine(x,y,x+3,y+1)
        p.setClipping(False);p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(color).lighter(115),1))
        p.drawRoundedRect(QRectF(14,14,w-29,h-29),25,25)
        # Add seams and folds to the cushion texture.
        p.setPen(QPen(outline,1.1))
        for x,y,dx,dy in [(20,22,16,9),(w-22,h-23,-17,-7)]:
            crease=QPainterPath(QPointF(x,y));crease.quadTo(x+dx*.25,y+dy,x+dx,y+dy);p.drawPath(crease)
        p.end();self._detail_texture_cache[key]=image;return image

    def _record_texture(self):
        if 'vinyl' in self._detail_texture_cache:return self._detail_texture_cache['vinyl']
        image=QPixmap(240,240);image.fill(Qt.GlobalColor.transparent)
        p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#545e54'),2));p.setBrush(QColor('#677267'));p.drawEllipse(QRectF(3,3,234,234))
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#859184'),.8))
        for r in range(47,111,5):p.drawEllipse(QPointF(120,120),r,r)
        p.setBrush(QColor('#c6b397'));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QPointF(120,120),32,32)
        p.setBrush(QColor('#68705f'));p.drawEllipse(QPointF(120,120),4,4)
        # An off-centre label mark makes the record's rotation visible.
        p.setPen(QPen(QColor('#8e7057'),3));p.drawLine(113,102,128,108)
        p.setBrush(QColor('#a58b70'));p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(143,121),4,4)
        p.end();self._detail_texture_cache['vinyl']=image;return image

    def _print_texture(self,kind):
        key='print-'+kind
        if key in self._detail_texture_cache:return self._detail_texture_cache[key]
        image=QPixmap(360,440);image.fill(QColor('#eee7d6'))
        p=QPainter(image);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if kind=='record':
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#c2a18a'));p.drawEllipse(QRectF(55,55,250,250))
            p.setBrush(QColor('#829280'));p.drawEllipse(QRectF(105,105,150,150))
            p.setBrush(QColor('#e9dfc9'));p.drawEllipse(QRectF(161,161,38,38))
            p.setPen(QPen(QColor('#727c6b'),1.3));p.drawLine(75,330,285,330)
            p.setFont(QFont('Georgia',17));p.drawText(QRectF(20,348,320,40),Qt.AlignmentFlag.AlignCenter,'SLOW DAYS')
        else:
            p.setPen(QPen(QColor('#82917a'),4,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            stem=QPainterPath(QPointF(180,365));stem.cubicTo(155,280,195,180,165,80);p.drawPath(stem)
            for n in range(6):
                x=177+math.sin(n)*9;y=125+n*35;direction=-1 if n%2 else 1
                leaf=QPainterPath(QPointF(x,y));leaf.cubicTo(x+direction*24,y-40,x+direction*68,y-43,x+direction*75,y-32)
                leaf.cubicTo(x+direction*60,y-12,x+direction*25,y+6,x,y)
                p.setBrush(QColor('#a0ad91'));p.setPen(QPen(QColor('#7e8e76'),1.8));p.drawPath(leaf)
            p.setPen(QColor('#92977e'));p.setFont(QFont('Georgia',12));p.drawText(QRectF(10,380,340,30),Qt.AlignmentFlag.AlignCenter,'FIELD STUDY / 04')
        rng=random.Random(71)
        for n in range(1200):p.setPen(QColor(84,77,60,16));p.drawPoint(rng.randrange(360),rng.randrange(440))
        p.end();self._detail_texture_cache[key]=image;return image

    def _outdoor_color(self, value):
        if not self.night_mode:
            return QColor(value)
        palette = {
            '#d8dfd8': '#233247', '#ede9dc': '#e5ddc4', '#e4e7df': '#2d3e52',
            '#b5c4bb': '#405765', '#9eafa1': '#354e59', '#839a87': '#2e474d',
            '#748a75': '#273e43', '#89947d': '#e6ba78', '#c7c5a8': '#68756d',
        }
        return QColor(palette[value]) if value in palette else self._color(value)

    def _landscape_image(self):
        """Cache the landscape shared by the window and outside view."""
        if self.night_mode in self._landscapes:
            return self._landscapes[self.night_mode]
        image=QPixmap(1200,740); image.fill(self._outdoor_color('#d8dfd8'))
        p=QPainter(image); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._outdoor_color('#ede9dc')); p.drawEllipse(QPointF(850,145),45,45)
        if self.night_mode:
            stars = random.Random(39)
            p.setPen(Qt.PenStyle.NoPen)
            for n in range(54):
                x, y = stars.randrange(30, 1170), stars.randrange(25, 270)
                p.setBrush(QColor(215, 222, 224, stars.randrange(85, 170)))
                radius = .8 if n % 5 else 1.35
                p.drawEllipse(QPointF(x, y), radius, radius)
        # Use a few filled paths for the cloud shapes.
        p.setBrush(self._outdoor_color('#e4e7df'))
        for x,y,w in [(120,95,260),(530,210,230),(915,70,210)]:
            path=QPainterPath(QPointF(x,y+24)); path.cubicTo(x+w*.1,y-10,x+w*.22,y-18,x+w*.35,y+5)
            path.cubicTo(x+w*.53,y-32,x+w*.66,y-12,x+w*.74,y+9)
            path.cubicTo(x+w*.91,y-2,x+w,y+8,x+w,y+24)
            path.closeSubpath(); p.drawPath(path)
        hills=[('#b5c4bb',330,42,1.1),('#9eafa1',410,46,2.7),('#839a87',500,38,.5),('#748a75',625,65,2.0)]
        for layer,(col,base,amplitude,offset) in enumerate(hills):
            path=QPainterPath(QPointF(-10,740)); path.lineTo(-10,base)
            for x in range(-10,1221,12):
                y=base+math.sin(x/185+offset)*amplitude+math.sin(x/83+offset)*amplitude*.14
                path.lineTo(x,y)
            path.lineTo(1220,740);path.closeSubpath();p.fillPath(path,self._outdoor_color(col))
            p.setPen(QPen(self._outdoor_color('#68816c'),.65));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(path)
            p.save();p.setClipPath(path)
            wash=random.Random(143+layer)
            # Keep the grain faint so it does not obscure the landscape.
            for mark in range(700):
                x,y=wash.randrange(-30,1200),wash.randrange(int(base-amplitude),740)
                stroke=QColor('#e1e5d8' if mark%3 else '#4b6953');stroke.setAlpha(wash.randrange(5,17))
                p.setPen(QPen(stroke,wash.uniform(.35,1.5),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
                length=wash.randrange(4,34)
                p.drawLine(QPointF(x,y),QPointF(x+length,y+wash.uniform(-2,2)))
            p.restore();p.setPen(Qt.PenStyle.NoPen)
        # A narrowing path suggests distance.
        path=QPainterPath(QPointF(520,740));path.cubicTo(600,650,860,650,790,582)
        path.cubicTo(760,551,720,535,742,510);path.lineTo(751,510)
        path.cubicTo(730,545,812,553,825,591);path.cubicTo(870,665,665,693,662,740)
        p.fillPath(path,self._outdoor_color('#c7c5a8'))
        def tree(x,y,size,col):
            p.setPen(QPen(self._outdoor_color('#686c58'),max(1.2,size*.025),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(x,y),QPointF(x-3,y-size*.75))
            p.drawLine(QPointF(x,y-size*.38),QPointF(x+size*.22,y-size*.62))
            p.setPen(QPen(self._outdoor_color('#637461'),.8));p.setBrush(self._outdoor_color(col))
            shape=QPainterPath(QPointF(x-size*.27,y-size*.3))
            shape.cubicTo(x-size*.63,y-size*.46,x-size*.48,y-size*.78,x-size*.24,y-size*.78)
            shape.cubicTo(x-size*.18,y-size*1.16,x+size*.24,y-size*1.12,x+size*.28,y-size*.83)
            shape.cubicTo(x+size*.59,y-size*.85,x+size*.62,y-size*.49,x+size*.32,y-size*.4)
            shape.cubicTo(x+size*.28,y-size*.19,x-size*.1,y-size*.15,x-size*.27,y-size*.3)
            p.drawPath(shape)
            p.save();p.setClipPath(shape)
            leaves=random.Random(round(x))
            for mark in range(65):
                lx=x+leaves.uniform(-.5,.5)*size;ly=y-leaves.uniform(.24,1.05)*size
                p.setPen(QPen(QColor(205,214,187,35),max(.6,size*.008),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
                p.drawLine(QPointF(lx,ly),QPointF(lx+size*.045,ly-size*.02))
            p.restore()
            p.setPen(QPen(self._outdoor_color('#8e9d83'),max(.65,size*.009),Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            vein=QPainterPath(QPointF(x,y-size*.25));vein.cubicTo(x+size*.03,y-size*.47,x-size*.06,y-size*.66,x-3,y-size*.82);p.drawPath(vein)
            p.drawLine(QPointF(x,y-size*.49),QPointF(x-size*.18,y-size*.63))
            p.drawLine(QPointF(x,y-size*.60),QPointF(x+size*.15,y-size*.76))
        for x,y,size,col in [(160,480,62,'#879e86'),(230,470,48,'#91a38d'),(1040,465,56,'#8c9e87'),(995,484,68,'#83987d'),(87,649,142,'#6d826b'),(1110,690,190,'#627860'),(340,600,84,'#7f9275')]:
            tree(x,y,size,col)
        # Add distant landmarks to establish scale.
        p.setPen(QPen(self._outdoor_color('#929780'),.7));p.setBrush(self._outdoor_color('#d7d3bd'))
        p.drawPolygon(QPolygonF([QPointF(655,470),QPointF(691,464),QPointF(691,440),QPointF(655,445)]))
        p.setBrush(self._outdoor_color('#b19b84'))
        p.drawPolygon(QPolygonF([QPointF(650,446),QPointF(672,428),QPointF(697,440),QPointF(691,445),QPointF(672,434),QPointF(655,450)]))
        p.setBrush(self._outdoor_color('#89947d'));p.drawRect(QRectF(667,450,6,9));p.drawRect(QRectF(682,448,5,8))
        p.setPen(QPen(self._outdoor_color('#8e8f72'),1.2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        posts=[(861,629,22),(905,651,27),(962,684,32),(1036,731,38)]
        for px,py,ph in posts:p.drawLine(QPointF(px,py),QPointF(px-2,py-ph))
        p.setBrush(Qt.BrushStyle.NoBrush)
        fence=QPainterPath(QPointF(858,616));fence.cubicTo(909,629,976,680,1034,707)
        p.setPen(QPen(self._outdoor_color('#8e8f72'),.8));p.drawPath(fence)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(self._outdoor_color('#91a097'),1.2))
        for bx,by in [(420,235),(452,223)]:
            bird=QPainterPath(QPointF(bx-7,by-2));bird.quadTo(bx-2,by-4,bx,by+1);bird.quadTo(bx+3,by-3,bx+8,by-2);p.drawPath(bird)
        # A fixed seed keeps the grass and grain identical in both views.
        rng=random.Random(107)
        for n in range(1500):
            x,y=rng.randrange(1200),rng.randrange(740)
            p.setPen(QColor(61,71,57,rng.randrange(3,10)));p.drawPoint(x,y)
        for n in range(90):
            x=rng.randrange(1200);y=rng.randrange(600,735)
            p.setPen(QPen(QColor(58,80,56,55),.8))
            p.drawLine(QPointF(x,y),QPointF(x-2,y-5))
        p.end();self._landscapes[self.night_mode]=image
        return image

    def _shell(self,p):
        self._polygon(p,[(0,0,0),(8,0,0),(8,5.8,0),(0,5.8,0)],'#d7c6ab')
        # Floor planks.
        for n in range(15):
            y=n*.4
            self._line(p,[(0,y,.005),(8,y,.005)],'#b9a88f',.65)
            for x in [1.0+(n%3)*.85,3.8+(n%2)*1.1,7.1]:
                self._line(p,[(x,y,.006),(x,min(5.8,y+.4),.006)],'#b9a88f',.6)
        self._polygon(p,[(0,5.8,0),(8,5.8,0),(8,5.8,3.5),(0,5.8,3.5)],'#e5dfcf')
        self._polygon(p,[(0,0,0),(0,5.8,0),(0,5.8,3.5),(0,0,3.5)],'#d3d6c7')
        self._line(p,[(0,5.78,.12),(8,5.78,.12)],'#b2ad9c',4)
        self._line(p,[(.02,0,.12),(.02,5.8,.12)],'#aeb19f',4)
        self._map_image(p,self._landscape_image(),WINDOW,night_shade=False)
        self._line(p,list(WINDOW)+[WINDOW[0]],'#777e70',7)
        self._line(p,[(2.625,5.77,1.22),(2.625,5.77,3.1)],'#858b7b',5)
        self._line(p,[(.6,5.77,2.05),(4.65,5.77,2.05)],'#858b7b',4)
        self._line(p,[(.47,5.69,1.16),(4.79,5.69,1.16)],'#a99578',6)
        # Window blind.
        self._polygon(p,[(.48,5.67,3.21),(4.78,5.67,3.21),(4.78,5.67,3.04),(.48,5.67,3.04)],'#c6bda5')
        self._line(p,[(.48,5.66,3.08),(4.78,5.66,3.08)],'#a79f89',1)
        # Wall prints use the same positions in every camera view.
        self._polygon(p,[(.025,3.18,2.4),(.025,4.15,2.4),(.025,4.15,1.68),(.025,3.18,1.68)],'#ab967a')
        self._polygon(p,[(.03,3.25,2.33),(.03,4.08,2.33),(.03,4.08,1.75),(.03,3.25,1.75)],'#eee8d7')
        self._map_image(p,self._print_texture('botanical'),[(.04,3.25,2.33),(.04,4.08,2.33),(.04,4.08,1.75),(.04,3.25,1.75)])
        self._polygon(p,[(.025,1.10,2.62),(.025,2.12,2.62),(.025,2.12,1.46),(.025,1.10,1.46)],'#aa9478')
        self._map_image(p,self._print_texture('record'),[(.035,1.17,2.55),(.035,2.05,2.55),(.035,2.05,1.53),(.035,1.17,1.53)])
        # Reading-area rug.
        self._ellipse(p,5.8,2.15,.018,1.6,1.27,'#c8c8b4')
        for n in range(6):
            self._ellipse(p,5.8,2.15,.02+n*.0001,1.54-n*.12,1.21-n*.10,'#c9c9b6' if n%2 else '#bfc2ab')
        for x,y,rx,ry in [(2.7,4.45,1.9,.85),(6.35,5.4,1.3,.5),(6.2,2.25,.9,.9),(1.8,1.65,1.4,.7),(7.5,4.1,.4,.4)]:
            self._shadow(p,x,y,rx,ry)

    def _group(self, centre):
        if self.faces:
            self.groups.append((self._depth([centre]), self.faces))
            self.faces = []

    def _build_furnishings(self):
        # Desk top and legs.
        for x in [1.06,3.78]:
            for y in [4.04,5.05]:self._box(x,y,0,.12,.12,1.05,'#a98c6b')
        self._box(1.07,4.05,.77,.85,1.0,.26,'#baa07e',True)
        self._box(1.36,4.025,.86,.26,.025,.035,'#777f70')
        self._box(.9,3.92,1.05,3.2,1.35,.12,'#b99b76',True)
        # Exercise book and pencil.
        self._box(2.0,4.14,1.18,.88,.62,.025,'#ece8d9')
        self._face([(2.44,4.15,1.207),(2.45,4.15,1.207),(2.45,4.75,1.207),(2.44,4.75,1.207)],'#c0b79f')
        for n in range(5):
            y=4.24+n*.075
            self._face([(2.07,y,1.21),(2.34,y,1.21),(2.34,y+.009,1.21),(2.07,y+.009,1.21)],'#cbc8b9')
        self._box(3.0,4.18,1.18,.025,.58,.025,'#777e6c')
        # The lamp is static; its light is added in a cached layer.
        self._cylinder(3.53,4.82,1.18,.18,.035,'#6f7d72')
        self._cylinder(3.53,4.82,1.20,.025,.5,'#687367')
        self._cylinder(3.53,4.82,1.65,.26,.19,'#a8b3a1',.12)
        self._cylinder(1.48,4.83,1.18,.10,.16,'#b89984')
        self._cylinder(1.48,4.83,1.345,.078,.004,'#665a4a')
        for n in range(12):
            a=n*math.pi/6; b=(n+1)*math.pi/6
            self._face([(1.57+math.cos(a)*.065,4.74,1.26+math.sin(a)*.066),
                        (1.57+math.cos(b)*.065,4.74,1.26+math.sin(b)*.066),
                        (1.57+math.cos(b)*.039,4.74,1.26+math.sin(b)*.040),
                        (1.57+math.cos(a)*.039,4.74,1.26+math.sin(a)*.040)],'#b89984','ceramic')
        self._face([(3.53,4.82,1.655)],None,'lamp_glow')
        self._group((2.5,4.6,.8))
        # Desk chair.
        for x in [2.20,2.83]:
            for y in [3.1,3.62]:self._box(x,y,0,.075,.075,.57,'#997e62')
        self._box(2.12,3.02,.53,.88,.76,.12,'#b98d78')
        self._box(2.14,3.04,.65,.84,.12,.6,'#bd9984')
        self._group((2.5,3.3,.6))
        # Three shelf levels above a solid base.
        self._box(5.08,5.06,.13,2.5,.7,.23,'#b6a081',True)
        self._box(5.08,5.64,.36,2.5,.12,2.35,'#c2ae8e',True)
        for x in [5.08,7.46]:self._box(x,5.06,.36,.12,.7,2.35,'#b39b7b',True)
        for z in SHELF_BOARD_BASES:
            self._box(5.08,5.03,z,2.5,.74,SHELF_BOARD_THICKNESS,'#b8a181',True)
        self._build_books()
        self.faces = self._ordered_cabinet_faces(self.faces)
        self._group((6.3,5.4,1.4))
        # Reading chair.
        for x in [5.63,6.73]:
            for y in [1.62,2.66]:self._box(x,y,.03,.10,.1,.37,'#a48b6d')
        self._box(5.47,1.55,.35,1.5,1.28,.26,'#8c9e8a')
        self._box(5.45,2.65,.55,1.54,.22,1.05,'#91a28e')
        for x in [5.38,6.84]:self._box(x,1.57,.52,.18,1.28,.34,'#839681')
        self._face([(5.54,2.625,1.53),(6.89,2.625,1.53),(6.89,2.625,.66),(5.54,2.625,.66)],None,False,self._fabric_texture('back','#91a28e',360,240))
        self._face([(5.58,2.57,.625),(6.81,2.57,.625),(6.81,1.66,.625),(5.58,1.66,.625)],None,False,self._fabric_texture('seat','#9dac96',360,270))
        self._face([(5.70,2.59,1.30),(6.32,2.59,1.35),(6.34,2.37,.79),(5.71,2.37,.78)],None,False,self._fabric_texture('pillow','#d3b69d',220,210))
        self._group((6.2,2.2,.7))
        # Side table and journal.
        self._cylinder(4.9,2.65,.05,.06,.59,'#a28d70')
        self._cylinder(4.9,2.65,.64,.46,.055,'#b99f7c')
        self._box(4.65,2.48,.70,.38,.35,.06,'#9d8378')
        self._group((4.9,2.65,.4))
        # Music console and record sleeve.
        self._box(.48,1.13,.18,2.45,1.0,.66,'#b49b7b',True)
        for x in [.65,2.65]:self._box(x,1.28,0,.10,.65,.18,'#9f896e')
        self._box(.65,1.085,.33,1.00,.045,.36,'#d0c8b4')
        for n in range(12):self._box(.69+n*.075,1.055,.36,.012,.009,.30,'#aca98f')
        self._box(1.77,1.08,.32,.96,.04,.39,'#b99e7d',True)
        self._box(1.85,1.045,.42,.38,.02,.17,'#626f64')
        for x in [2.44,2.61]:self._box(x,1.025,.43,.075,.045,.075,'#716e60')
        self._box(.95,1.35,.85,1.16,.64,.08,'#a48d70')
        self._cylinder(1.45,1.67,.94,.235,.016,'#62675d')
        self._face([(1.21,1.91,.968),(1.69,1.91,.968),(1.69,1.43,.968),(1.21,1.43,.968)],None,'record',self._record_texture())
        self._box(1.87,1.59,.96,.025,.25,.018,'#6d7367')
        self._group((1.7,1.6,.5))
        # Fixed branches and leaves.
        self._cylinder(7.45,4.20,0,.25,.46,'#b49a82',.30)
        for n in range(11):
            angle=n*2.399
            base=(7.45,4.2,.44)
            breeze=0.0  # Animate leaves over the cached plant geometry.
            tip=(7.45+math.cos(angle)*(.32+(n%3)*.09)+breeze,4.2+math.sin(angle)*.37,.85+(n%4)*.16)
            mid=tuple((base[k]+tip[k])*.5 for k in range(3))
            left=(mid[0]-math.sin(angle)*.23,mid[1]+math.cos(angle)*.23,mid[2]+.18)
            right=(mid[0]+math.sin(angle)*.21,mid[1]-math.cos(angle)*.21,mid[2]-.04)
            self._face([base,left,tip,right], '#879a7d' if n%2 else '#748b71', 'leaf')
        self._group((7.45,4.2,.6))

    def _book_image(self,name):
        if not name:return QPixmap()
        path=Path(name)
        if not path.is_absolute():
            if self.data_root is None:return QPixmap()
            path=Path(self.data_root)/path
        if str(path) not in self._book_image_cache:
            reader=QImageReader(str(path));reader.setAutoTransform(True)
            size=reader.size()
            if max(size.width(),size.height())>768:reader.setScaledSize(size.scaled(QSize(768,768),Qt.AspectRatioMode.KeepAspectRatio))
            self._book_image_cache[str(path)]=QPixmap.fromImage(reader.read())
        return self._book_image_cache[str(path)]

    def _book_surface_texture(self, book, facing, seed):
        key = (book['id'], facing)
        if key not in self._book_texture_cache:
            width = 256 if facing == 'cover' else 72
            image = QPixmap(width, 384)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            appearance = {'template': 'linen', 'cover_color': book.get('color', '#889682'),
                          'spine_color': book.get('color', '#889682')}
            appearance.update(book.get('book_appearance', {}))
            draw_book(painter, QRectF(image.rect()), appearance, book['title'], facing,
                      self._book_image, seed, dimensional=False)
            painter.end()
            self._book_texture_cache[key] = image
        return self._book_texture_cache[key]

    def _book_page_texture(self):
        key = ('page_edges',)
        if key not in self._book_texture_cache:
            image = QPixmap(72, 384)
            image.fill(QColor('#d7cdb5'))
            painter = QPainter(image)
            painter.setPen(QPen(QColor(118, 106, 84, 46), 1))
            for y in range(4, image.height(), 7):
                painter.drawLine(0, y, image.width(), y)
            painter.end()
            self._book_texture_cache[key] = image
        return self._book_texture_cache[key]

    def _build_books(self):
        self.book_volumes = {}
        for index, book in enumerate(self.books):
            slot = book.get('book_slot', index if index < 30 else None)
            facing = book.get('book_facing', 'spine')
            if type(slot) is not int or not 0 <= slot < 30 or facing not in ('spine', 'cover'):
                continue
            if facing == 'cover' and slot % 10 > 7:
                continue
            seed = int.from_bytes(hashlib.sha256(book['id'].encode()).digest()[:4], 'little')
            volume = book_volume(slot, facing, seed)
            self.book_volumes[book['id']] = volume
            appearance = book.get('book_appearance', {})
            front_color = appearance.get('cover_color' if facing == 'cover' else 'spine_color',
                                         book.get('color', '#889682'))
            cover_color = appearance.get('cover_color', book.get('color', '#889682'))
            # Cover-out books show binding on the left and paper on the right.
            right_side = self.current_camera.eye[0] > volume.x+volume.width/2
            side_facing = 'pages' if facing == 'cover' and right_side else (
                'spine' if facing == 'cover' else 'cover')
            side_color = '#d7cdb5' if side_facing == 'pages' else appearance.get(
                'spine_color' if side_facing == 'spine' else 'cover_color',
                book.get('color', '#889682'))
            side_texture = (self._book_page_texture() if side_facing == 'pages' else
                            self._book_surface_texture(book, side_facing, seed))
            # Project flat artwork onto the book planes to avoid double perspective.
            self._face(volume.front, front_color, False,
                       self._book_surface_texture(book, facing, seed), book)
            self._face(volume.side(self.current_camera.eye), side_color, False,
                       side_texture, book)
            self._face(volume.top, cover_color)
            x, y, z = volume.x, volume.y, volume.z+volume.height+.0006
            # The paper block is inset between the cover boards, on one plane.
            inset_x = .013 if facing == 'spine' else .018
            inset_y = .045 if facing == 'spine' else .009
            pages = [(x+inset_x,y+inset_y,z), (x+volume.width-inset_x,y+inset_y,z),
                     (x+volume.width-inset_x,y+volume.depth-.009,z),
                     (x+inset_x,y+volume.depth-.009,z)]
            self._face(pages, '#d7cdb5', 'ceramic')

    def _face_depth_plane(self, points, polygon):
        """Find the affine depth plane for a projected face."""
        a = polygon[0]
        da = self._depth([points[0]])
        for index in range(2, len(points)):
            b, c = polygon[1], polygon[index]
            bx, by, cx, cy = b.x()-a.x(), b.y()-a.y(), c.x()-a.x(), c.y()-a.y()
            determinant = bx*cy-cx*by
            if abs(determinant) < 1e-8:
                continue
            db = self._depth([points[1]])-da
            dc = self._depth([points[index]])-da
            x_coefficient = (db*cy-dc*by)/determinant
            y_coefficient = (bx*dc-cx*db)/determinant
            return x_coefficient, y_coefficient, da-x_coefficient*a.x()-y_coefficient*a.y()
        return None

    def _ordered_cabinet_faces(self, faces):
        """Sort overlapping shelf and book faces by depth.
        Use overlap depth rather than face centres so boards occlude books correctly."""
        descriptors = []
        for face in faces:
            polygon = QPolygonF([self.project_world(point) for point in face[1]])
            path = QPainterPath()
            path.addPolygon(polygon)
            path.closeSubpath()
            descriptors.append((polygon.boundingRect(), path,
                                self._face_depth_plane(face[1], polygon)))
        following = [set() for _ in faces]
        incoming = [0 for _ in faces]
        for left, (left_bounds, left_path, left_plane) in enumerate(descriptors):
            if left_plane is None:
                continue
            for right in range(left+1, len(faces)):
                right_bounds, right_path, right_plane = descriptors[right]
                if right_plane is None or not left_bounds.intersects(right_bounds):
                    continue
                overlap = left_path.intersected(right_path).toFillPolygon()
                if len(overlap) < 3:
                    continue
                area = abs(sum(overlap[n].x()*overlap[(n+1)%len(overlap)].y()
                               -overlap[(n+1)%len(overlap)].x()*overlap[n].y()
                               for n in range(len(overlap))))/2
                if area < .002:
                    continue
                point = QPointF(sum(p.x() for p in overlap)/len(overlap),
                                sum(p.y() for p in overlap)/len(overlap))
                left_depth = left_plane[0]*point.x()+left_plane[1]*point.y()+left_plane[2]
                right_depth = right_plane[0]*point.x()+right_plane[1]*point.y()+right_plane[2]
                if abs(left_depth-right_depth) < 1e-5:
                    continue
                far, near = (left,right) if left_depth > right_depth else (right,left)
                following[far].add(near)
                incoming[near] += 1
        ready = [(-faces[index][0],index) for index,count in enumerate(incoming) if not count]
        heapq.heapify(ready)
        result, visited = [], set()
        while ready:
            _, index = heapq.heappop(ready)
            if index in visited:
                continue
            visited.add(index)
            result.append(faces[index])
            for near in following[index]:
                incoming[near] -= 1
                if not incoming[near]:
                    heapq.heappush(ready, (-faces[near][0],near))
        # Use a stable depth fallback for ambiguous coplanar contacts.
        remaining = [index for index in range(len(faces)) if index not in visited]
        self.cabinet_order_cycles = len(remaining)
        result.extend(faces[index] for index in sorted(remaining,key=lambda i:faces[i][0],reverse=True))
        return result

    def _draw_face(self, painter, face):
        depth, points, color, grain, texture, book = face
        polygon = QPolygonF([self.project_world(point) for point in points])
        if grain == 'lamp_glow':
            if not self.night_mode:
                return QRectF()
            centre = polygon[0]
            radius = self._projection_values()[4] * .17
            glow = QRadialGradient(centre, radius)
            glow.setColorAt(0, QColor(255, 229, 170, 200))
            glow.setColorAt(.22, QColor(244, 203, 137, 125))
            glow.setColorAt(1, QColor(244, 203, 137, 0))
            area = QRectF(centre.x()-radius, centre.y()-radius*.6, radius*2, radius*1.2)
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(area)
            painter.restore()
            return area
        if color is not None:
            self._polygon(painter, points, color, grain != 'ceramic')
        if grain is True and len(points) == 4:
            a, b, c, d = points
            for n in range(1, 5):
                t = n / 5
                u = tuple(a[k]*(1-t)+d[k]*t for k in range(3))
                v = tuple(b[k]*(1-t)+c[k]*t for k in range(3))
                mid = tuple((u[k]+v[k])*.5 for k in range(3))
                mid = (mid[0], mid[1]+math.sin(n*2.7)*.018, mid[2]+math.sin(n)*.004)
                self._line(painter, [u, mid, v], '#ac987b', .35)
        if texture is not None:
            self._map_image(painter, texture, points)
        if self.night_mode and len(points) == 4:
            # Cache the light below the book and lamp in the drawing order.
            if all(abs(point[2] - 1.17) < .0001 for point in points):
                clip = QPainterPath()
                clip.addPolygon(polygon)
                clip.closeSubpath()
                source = self.project_world((3.35, 4.62, 1.17))
                radius = self._projection_values()[4] * .95
                gradient = QRadialGradient(source, radius)
                gradient.setColorAt(0, QColor(247, 204, 130, 165))
                gradient.setColorAt(.35, QColor(232, 184, 105, 95))
                gradient.setColorAt(1, QColor(232, 184, 105, 0))
                painter.save()
                painter.setClipPath(clip)
                painter.fillRect(clip.boundingRect(), gradient)
                painter.restore()
        return polygon.boundingRect().adjusted(-3, -3, 3, 3)

    def _new_layer(self):
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(max(1, round(self.width()*dpr)), max(1, round(self.height()*dpr)))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        return pixmap, painter

    def _cache_key(self):
        return (self.current_view, self.width(), self.height(), self.devicePixelRatioF(),
                self.night_mode, self._visual_revision, self._view_offset)

    def _build_static_layers(self):
        """Cache static layers between the animated objects.
        Crop later layers to their bounds and retain the matching book hit regions."""
        self.static_build_count += 1
        self.faces, self.groups = [], []
        self._build_furnishings()
        faces = [face for _, group in sorted(self.groups, key=lambda group: group[0], reverse=True)
                 for face in group]
        operations, hit_rectangles = [], OrderedDict()
        layer, painter = self._new_layer()
        painter.fillRect(self.rect(), QColor('#1f2831' if self.night_mode else PAPER))
        self._shell(painter)
        painter.setPen(QPen(QColor(167, 177, 183, 9) if self.night_mode else QColor(85, 78, 63, 14), .65))
        paper = random.Random(32)
        for n in range(1600):
            x, y = paper.randrange(max(1, self.width())), paper.randrange(max(1, self.height()))
            painter.drawLine(x, y, x+1, y)
        bounds = QRectF(self.rect())
        has_static = True

        def flush():
            nonlocal layer, painter, bounds, has_static
            if painter is None:
                return
            painter.end()
            if has_static:
                dpr = layer.devicePixelRatioF()
                occupied = bounds.intersected(QRectF(self.rect()))
                pixels = QRect(math.floor(occupied.left()*dpr), math.floor(occupied.top()*dpr),
                               max(1, math.ceil(occupied.right()*dpr)-math.floor(occupied.left()*dpr)),
                               max(1, math.ceil(occupied.bottom()*dpr)-math.floor(occupied.top()*dpr)))
                image = layer.copy(pixels)
                image.setDevicePixelRatio(dpr)
                operations.append(('static', image, QPointF(pixels.x()/dpr, pixels.y()/dpr)))
            layer, painter, bounds, has_static = None, None, QRectF(), False

        leaf_index = 0
        for face in faces:
            depth, points, color, grain, texture, book = face
            if grain == 'record':
                flush()
                operations.append(('record', points, texture))
                continue
            if grain == 'leaf':
                flush()
                operations.append(('leaf', points, color, leaf_index))
                leaf_index += 1
                continue
            if painter is None:
                layer, painter = self._new_layer()
            occupied = self._draw_face(painter, face)
            bounds = occupied if not has_static else bounds.united(occupied)
            has_static = True
            if book is not None:
                polygon = QPolygonF([self.project_world(point) for point in points])
                pid = book['id']
                previous = hit_rectangles.pop(pid, QRectF())
                hit_rectangles[pid] = previous.united(polygon.boundingRect())
        flush()
        return {'operations': operations,
                'book_hits': [(rect, pid) for pid, rect in hit_rectangles.items()]}

    def _static_layers(self):
        key = self._cache_key()
        if key not in self._scene_cache:
            self._scene_cache[key] = self._build_static_layers()
            while len(self._scene_cache) > self._cache_limit:
                self._scene_cache.popitem(last=False)
        self._scene_cache.move_to_end(key)
        return self._scene_cache[key]

    def _draw_record(self, painter, points, texture):
        a, b, c, d = [self.project_world(point) for point in points]
        transform = QTransform((b.x()-a.x())/texture.width(), (b.y()-a.y())/texture.width(),
                               (d.x()-a.x())/texture.height(), (d.y()-a.y())/texture.height(), a.x(), a.y())
        painter.save()
        painter.setTransform(transform, True)
        painter.translate(texture.width()/2, texture.height()/2)
        painter.rotate(self.record_angle)
        painter.drawPixmap(QPointF(-texture.width()/2, -texture.height()/2), self._night_texture(texture))
        painter.restore()

    def _draw_leaf(self, painter, points, color, index):
        breeze = math.sin(self._elapsed*.55+index*.7)*.018
        moved = []
        for point, factor in zip(points, (0, .5, 1, .5)):
            moved.append((point[0]+breeze*factor, point[1], point[2]))
        a, b, c, d = [self.project_world(point) for point in moved]
        leaf = QPainterPath(a)
        leaf.quadTo(b, c)
        leaf.quadTo(d, a)
        painter.setPen(QPen(self._color('#65795f'), .65))
        painter.setBrush(self._color(color))
        painter.drawPath(leaf)
        vein = QPainterPath(a)
        vein.quadTo((a+c)*.5+QPointF(2, -3), c)
        painter.setPen(QPen(self._color('#b3bca3'), .65))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(vein)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.hotspot_hits = []
        if self.outdoor:
            image = self._landscape_image()
            scale = max(self.width()/image.width(), self.height()/image.height())
            rect = QRectF((self.width()-image.width()*scale)/2, (self.height()-image.height()*scale)/2,
                          image.width()*scale, image.height()*scale)
            painter.drawPixmap(rect, image, QRectF(image.rect()))
            self.book_hits = []
            painter.end()
            return
        entry = self._static_layers()
        projects = {book['id']: book for book in self.books}
        self.book_hits = [(rect, projects[pid]) for rect, pid in entry['book_hits'] if pid in projects]
        for operation in entry['operations']:
            if operation[0] == 'static':
                painter.drawPixmap(operation[2], operation[1])
            elif operation[0] == 'record':
                self._draw_record(painter, operation[1], operation[2])
            else:
                self._draw_leaf(painter, operation[1], operation[2], operation[3])
        if self.hotspots_visible and not self.immersive:
            self._draw_hotspots(painter)
        painter.end()

    def showEvent(self, event):
        self._last_frame_time = self._clock()
        if self.motion:
            self.animation.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animation.stop()
        self._last_frame_time = self._clock()
        super().hideEvent(event)

    def _draw_hotspots(self,p):
        labels={'plan':'Notebook','focus':'Focus','collection':'Collection','music':'Music','outside':'Look outside'}
        keys=list(LANDMARKS) if self.current_view=='room' else ['outside']
        for key in keys:
            pos=self.project_world(LANDMARKS[key])
            if not self.rect().adjusted(25,90,-25,-95).contains(pos.toPoint()):continue
            active=self.hovered==key
            hit=QRectF(pos.x()-16,pos.y()-16,32,32)
            label_rect=None
            # Reveal scene labels on hover; keep the window action visible.
            if active or key == 'outside':
                p.setFont(QFont('Avenir Next',10))
                width=p.fontMetrics().horizontalAdvance(labels[key])+22
                label_rect=QRectF(pos.x()-width/2,pos.y()+12,width,27)
                hit=hit.united(label_rect)
            if any(hit.intersects(QRectF(exclusion)) for exclusion in self.ui_exclusions):
                continue
            radius=5.5 if active else 4
            p.setBrush(QColor('#ddd6bc' if self.night_mode else '#f5f0e4'));p.setPen(QPen(QColor('#a9b6a2' if self.night_mode else '#6d7968'),1.2));p.drawEllipse(pos,radius,radius)
            if label_rect is not None:
                p.setPen(QPen(QColor('#64766c' if self.night_mode else '#c5c1af'),.7));p.setBrush(QColor(42,53,64,244) if self.night_mode else QColor(246,243,233,240));p.drawRoundedRect(label_rect,4,4)
                p.setPen(QColor('#d9ddcf' if self.night_mode else '#535f51'));p.drawText(label_rect,Qt.AlignmentFlag.AlignCenter,labels[key])
            self.hotspot_hits.append((key,hit))

    def action_at(self,point):
        if self.immersive or self.outdoor or not self.hotspots_visible:return None
        for key,rect in self.hotspot_hits:
            if rect.contains(point):return key
        for rect,book in reversed(self.book_hits):
            if rect.contains(point):return 'project:'+book['id']
        return None

    def mouseMoveEvent(self,event):
        self.hovered=self.action_at(event.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if self.hovered else Qt.CursorShape.ArrowCursor)
        tip=''
        if self.hovered and self.hovered.startswith('project:'):
            book=next((b for b in self.books if 'project:'+b['id']==self.hovered),None)
            if book:tip=f"{book['title']} · {book['actual']} min invested"
        self.setToolTip(tip);self.update()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self._suppress_left_release=False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            if self._suppress_left_release:self._suppress_left_release=False;return
            action=self.action_at(event.position())
            if action:self.action_requested.emit(action)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and (self.immersive or self.outdoor):
            self._suppress_left_release=True
            self.action_requested.emit('leave-immersion');event.accept()
        else:super().mouseDoubleClickEvent(event)

    def leaveEvent(self,event):
        self.hovered=None;self.setToolTip('');self.update()
