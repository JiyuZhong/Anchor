"""Shared cover and spine drawing for the room and book editor."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainterPath, QPen


def _polygon(painter, points, color):
    path = QPainterPath(points[0])
    for point in points[1:]:
        path.lineTo(point)
    path.closeSubpath()
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(path, color)


def _image_cover(painter, rect, pixmap):
    """Crop an image to fill the face without changing its aspect ratio."""
    if pixmap is None or pixmap.isNull():
        return False
    scale = max(rect.width() / pixmap.width(), rect.height() / pixmap.height())
    source = QRectF((pixmap.width() - rect.width() / scale) / 2,
                    (pixmap.height() - rect.height() / scale) / 2,
                    rect.width() / scale, rect.height() / scale)
    painter.drawPixmap(rect, pixmap, source)
    return True


def draw_book(painter, rect, appearance, title, facing="spine", image_loader=None, seed=0,
              *, dimensional=True):
    """Draw a printed cover or spine.
    Set dimensional=False when the scene supplies the world projection."""
    if rect.width() <= 0 or rect.height() <= 0:
        return
    p = painter
    p.save()
    scale = rect.height() / 100
    cover = facing == "cover"
    template = appearance.get("template", "linen")
    color = QColor(appearance.get("cover_color" if cover else "spine_color", "#688380"))
    if not color.isValid():
        color = QColor("#688380")
    ink = QColor("#d9c7a5")
    depth = max(.8, (3.2 if cover else 2.2) * scale)
    rise = depth * .55
    # Scene textures stay flat because the room projection supplies depth.
    if dimensional:
        _polygon(p, [rect.topLeft(), rect.topRight(),
                     rect.topRight() + QPointF(depth, -rise),
                     rect.topLeft() + QPointF(depth, -rise)], QColor("#8a806a"))
        _polygon(p, [rect.topRight(), rect.bottomRight(),
                     rect.bottomRight() + QPointF(depth, -rise),
                     rect.topRight() + QPointF(depth, -rise)], color.darker(190))
    path = QPainterPath()
    if dimensional:
        path.addRoundedRect(rect, .75 * scale, .75 * scale)
    else:
        path.addRect(rect)
    gradient = QLinearGradient(rect.topLeft(), rect.topRight())
    gradient.setColorAt(0, color.darker(165))
    gradient.setColorAt(.16 if cover else .23, color.darker(108))
    gradient.setColorAt(.46, color.darker(112))
    gradient.setColorAt(1, color.darker(150))
    p.fillPath(path, gradient)
    p.setClipPath(path)
    image_path = appearance.get("cover_image" if cover else "spine_image", "")
    has_image = _image_cover(p, rect, image_loader(image_path)) if image_path and image_loader else False
    if has_image:
        # Apply the same shading to imported art as to the printed templates.
        lighting = QLinearGradient(rect.topLeft(), rect.topRight())
        lighting.setColorAt(0, QColor(5, 10, 15, 70))
        lighting.setColorAt(.28, QColor(5, 10, 15, 12))
        lighting.setColorAt(1, QColor(5, 10, 15, 55))
        p.fillRect(rect, lighting)
    else:
        # Fixed grain marks stay consistent when the room is redrawn.
        for n in range(1, int(rect.height() / max(1.5, 2.5 * scale))):
            y = rect.top() + n * max(1.5, 2.5 * scale)
            p.setPen(QPen(QColor(230, 220, 190, 7 + (n + seed) % 7), max(.35, .35 * scale)))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        if template == "classic":
            p.setPen(QPen(QColor(199, 172, 120, 150), max(.5, .65 * scale)))
            if cover:
                p.drawRect(rect.adjusted(5 * scale, 7 * scale, -5 * scale, -7 * scale))
            else:
                for fraction in (.08, .13, .85, .9):
                    y = rect.top() + rect.height() * fraction
                    p.drawLine(QPointF(rect.left() + scale, y), QPointF(rect.right() - scale, y))
        elif template == "botanical":
            p.setPen(QPen(QColor(194, 198, 154, 170), max(.45, .6 * scale)))
            stem_x = rect.center().x()
            stem_y = rect.bottom() - rect.height() * (.18 if cover else .12)
            length = rect.height() * (.24 if cover else .12)
            p.drawLine(QPointF(stem_x, stem_y), QPointF(stem_x - scale, stem_y - length))
            p.setBrush(QColor(177, 189, 146, 135))
            for n in range(3):
                y = stem_y - (n + 1) * length / 4
                direction = -1 if n % 2 else 1
                leaf = QPainterPath(QPointF(stem_x, y))
                leaf.quadTo(stem_x + direction * 7 * scale, y - 6 * scale,
                            stem_x + direction * 4 * scale, y - 7 * scale)
                leaf.quadTo(stem_x - direction * scale, y - 5 * scale, stem_x, y)
                p.drawPath(leaf)
        elif template == "celestial":
            centre = QPointF(rect.center().x(), rect.top() + rect.height() * (.26 if cover else .15))
            radius = min(rect.width() * .19, rect.height() * .062)
            p.setPen(QPen(QColor(213, 195, 151, 195), max(.6, .75 * scale)))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(centre, radius, radius)
            for n in range(4 if cover else 2):
                x = rect.left() + rect.width() * (.2 + ((seed + n * 17) % 60) / 100)
                y = rect.top() + rect.height() * (.1 + n * .105)
                p.drawLine(QPointF(x - scale, y), QPointF(x + scale, y))
                p.drawLine(QPointF(x, y - scale), QPointF(x, y + scale))
        title = appearance.get("title", "").strip() or title
        p.setPen(ink)
        font = QFont("Georgia" if template == "classic" else "Avenir Next")
        font.setPixelSize(max(5, round((8 if cover else 6.3) * scale)))
        p.setFont(font)
        if cover:
            text_rect = rect.adjusted(6 * scale, rect.height() * .36, -5 * scale, -rect.height() * .25)
            p.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, title)
        else:
            p.save()
            p.translate(rect.center())
            p.rotate(-90)
            available = max(0, int(rect.height() * .67))
            text = p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, available)
            p.drawText(QRectF(-available / 2, -rect.width() / 2, available, rect.width()),
                       Qt.AlignmentFlag.AlignCenter, text)
            p.restore()
    # The fold catches window light, while the hinge remains recessed.
    p.setPen(QPen(QColor(239, 225, 192, 65), max(.45, .55 * scale)))
    p.drawLine(rect.topLeft() + QPointF(1.3 * scale, scale),
               rect.bottomLeft() + QPointF(1.3 * scale, -scale))
    if cover:
        p.setPen(QPen(QColor(12, 12, 10, 95), max(.5, .8 * scale)))
        p.drawLine(rect.topLeft() + QPointF(4 * scale, scale),
                   rect.bottomLeft() + QPointF(4 * scale, -scale))
    p.restore()
