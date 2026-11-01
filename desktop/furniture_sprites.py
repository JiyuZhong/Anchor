"""Legacy furniture-atlas renderer, unused by the fixed study interface.
Source regions use the original 1774 x 887 atlas coordinates."""

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap, QRegion


# Rectangle coordinates are left, top, right, bottom (right/bottom exclusive).
SOURCE_REGIONS = {
    "basic_lamp": (40, 20, 350, 430),
    "linen_rug": (310, 169, 740, 367),
    "moon_lamp": (738, 68, 1040, 426),
    "jade_plant": (1065, 40, 1370, 420),
    "trailing_plant": (1369, 45, 1764, 442),
    "ceramic_vase": (42, 473, 316, 850),
    "star_mobile": (382, 420, 680, 858),
    "city_orb": (735, 470, 1044, 850),
    "attic_telescope": (1084, 440, 1368, 856),
    "garden_fern": (1369, 442, 1764, 856),
}

CLIP_POLYGONS = {
    "basic_lamp": ((40, 20), (350, 20), (350, 205), (285, 205),
                   (285, 430), (40, 430)),
    "linen_rug": ((390, 169), (655, 169), (740, 225),
                  (740, 367), (310, 367), (310, 235)),
}


class FurnitureSprites:
    """Cache cropped atlas sprites after QApplication has been created."""

    catalog = SOURCE_REGIONS

    def __init__(self, asset_path: str | Path):
        self._atlas = QPixmap(str(asset_path))
        self._cache = {}

    def get(self, item_id: str) -> QPixmap:
        if item_id in self._cache:
            return QPixmap(self._cache[item_id])
        if self._atlas.isNull() or item_id not in SOURCE_REGIONS:
            return QPixmap()

        sx, sy = self._atlas.width() / 1774, self._atlas.height() / 887
        left, top, right, bottom = SOURCE_REGIONS[item_id]
        source = QRectF(left * sx, top * sy, (right - left) * sx, (bottom - top) * sy)
        rendered = QPixmap(math.ceil(source.width()), math.ceil(source.height()))
        rendered.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rendered)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(-source.left(), -source.top())
        polygon = CLIP_POLYGONS.get(item_id)
        if polygon:
            clip = QPainterPath()
            clip.moveTo(polygon[0][0] * sx, polygon[0][1] * sy)
            for x, y in polygon[1:]:
                clip.lineTo(x * sx, y * sy)
            clip.closeSubpath()
            painter.setClipPath(clip)
        painter.drawPixmap(QPointF(0, 0), self._atlas)
        painter.end()

        # mask() is used only for the visible bounds; the original fractional
        # alpha is retained in the copied pixmap, so edges stay soft.
        tight = QRegion(rendered.mask()).boundingRect()
        if not tight.isEmpty():
            rendered = rendered.copy(tight)
        self._cache[item_id] = rendered
        return QPixmap(rendered)
