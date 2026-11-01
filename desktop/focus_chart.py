"""Hourly focus bars with a fixed inspection readout."""

from datetime import datetime
import math

from PySide6.QtCore import QEvent, QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QWidget


def _scene(widget):
    while widget is not None:
        scene = getattr(widget, "scene", None)
        if scene is not None:
            return scene
        widget = widget.parentWidget()
    return None


def _duration(minutes):
    seconds = max(0, round(minutes * 60))
    if seconds < 60:
        return f"{seconds} sec" if seconds else "0 min"
    whole_minutes, remainder = divmod(seconds, 60)
    hours, rest = divmod(whole_minutes, 60)
    if hours:
        return f"{hours}h {rest:02d}m"
    return f"{whole_minutes} min {remainder:02d}s" if remainder else f"{whole_minutes} min"


class FocusHourChart(QWidget):
    """Reserve space above the plot so inspection does not shift the layout.
    Only a change of hour updates the readout; the highlight fades separately."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.minutes = [0.0] * 24
        self.periods = [[] for _ in range(24)]
        self.hovered_hour = None
        self._highlight_hour = None
        self._highlight_opacity = 0.0
        self._summary_description = "No observed focus intervals."
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(100)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._set_highlight_opacity)
        self.setMinimumHeight(112)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("Observed focus minutes by local hour")

    def set_minutes(self, minutes, periods=None):
        self.minutes = list(minutes)
        if len(self.minutes) != 24:
            raise ValueError("The daily chart needs twenty-four hourly values.")
        self.periods = [list(values) for values in periods] if periods is not None else [[] for _ in range(24)]
        if len(self.periods) != 24:
            raise ValueError("The daily chart needs twenty-four interval lists.")
        self._summary_description = ", ".join(
            f"{hour:02d}:00 {value:.1f} minutes" for hour, value in enumerate(self.minutes) if value
        ) or "No observed focus intervals."
        self._clear_hover(immediate=True)
        self.update()

    def sizeHint(self):
        return QSize(400, 200)

    def plot_rect(self):
        return QRectF(29, 49, max(1, self.width()-42), max(1, self.height()-75))

    def readout(self):
        """Return the hour, duration and intervals, including DST offsets."""
        hour = self.hovered_hour
        if hour is None:
            return "Focus by hour", "min", "Local time"
        title = f"{hour:02d}:00 – {hour+1:02d}:00"
        value = _duration(self.minutes[hour])
        if self.minutes[hour] <= 0:
            return title, value, "No focus recorded"
        intervals = self.periods[hour]
        if not intervals:
            return title, value, "Observed focus"
        stamps = [(datetime.fromisoformat(item["started_at"]), datetime.fromisoformat(item["ended_at"]))
                  for item in intervals[:2]]
        offsets = {stamp.utcoffset() for pair in stamps for stamp in pair}
        ranges = []
        for start, end in stamps:
            precise = bool(start.second or end.second)
            pattern = "%H:%M:%S" if precise else "%H:%M"
            if len(offsets) > 1:
                pattern += " %z"
            ranges.append(f"{start.strftime(pattern)}–{end.strftime(pattern)}")
        detail = "  ·  ".join(ranges)
        if len(intervals) > 2:
            detail += f"  +{len(intervals)-2} more"
        return title, value, detail

    def _set_highlight_opacity(self, value):
        self._highlight_opacity = float(value)
        self.update()

    def _animate_highlight(self, opacity, *, immediate=False):
        self._fade.stop()
        scene = _scene(self)
        if immediate or not self.isVisible() or not getattr(scene, "motion", True):
            self._highlight_opacity = opacity
            return
        if abs(self._highlight_opacity-opacity) < .001:
            return
        self._fade.setStartValue(self._highlight_opacity)
        self._fade.setEndValue(opacity)
        self._fade.start()

    def _set_hover(self, hour):
        if hour == self.hovered_hour:
            return
        self.hovered_hour = hour
        if hour is not None:
            self._highlight_hour = hour
        self._animate_highlight(0.0 if hour is None else 1.0)
        if hour is None:
            self.setAccessibleDescription(self._summary_description)
        else:
            self.setAccessibleDescription(" · ".join(self.readout()))
        self.update()

    def _clear_hover(self, *, immediate=False):
        self.hovered_hour = None
        self._animate_highlight(0.0, immediate=immediate)
        if immediate:
            self._highlight_hour = None
        self.setAccessibleDescription(self._summary_description)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        night = bool(getattr(_scene(self), "night_mode", False))
        ink = QColor("#DDE5D3" if night else "#35483C")
        muted = QColor("#A7B59D" if night else "#7C8977")
        accent = QColor("#A7BE91" if night else "#7D9581")
        selected = QColor("#C4D7AC" if night else "#506E5C")
        grid = QColor("#465648" if night else "#DEE4D7")
        title, value, detail = self.readout()
        heading_font = QFont("Avenir Next", 10, QFont.Weight.Medium)
        painter.setFont(heading_font)
        value_width = max(32.0, QFontMetricsF(heading_font).horizontalAdvance(value)+12)
        painter.setPen(ink if self.hovered_hour is not None else muted)
        title_rect = QRectF(0, 0, max(1, self.width()-value_width-10), 22)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        painter.drawText(QRectF(self.width()-value_width, 0, value_width, 22),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, value)
        painter.setFont(QFont("Avenir Next", 8))
        painter.setPen(muted)
        detail = painter.fontMetrics().elidedText(detail, Qt.TextElideMode.ElideRight, max(1, self.width()-2))
        painter.drawText(QRectF(0, 23, self.width(), 17), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, detail)

        plot = self.plot_rect()
        maximum = max(15, math.ceil(max(self.minutes) / 15) * 15)
        column = plot.width()/24
        if self._highlight_hour is not None and self._highlight_opacity > .001:
            shade = QColor(accent)
            shade.setAlphaF(.11*self._highlight_opacity)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(shade)
            painter.drawRoundedRect(QRectF(plot.left()+self._highlight_hour*column,
                                          plot.top()-3, column, plot.height()+6), 3, 3)
        painter.setFont(QFont("Avenir Next", 8))
        for fraction in (0, .5, 1):
            y = plot.bottom() - fraction*plot.height()
            painter.setPen(QPen(grid, .7))
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            painter.setPen(muted)
            painter.drawText(QRectF(0, y-7, 24, 14), Qt.AlignmentFlag.AlignRight, f"{maximum*fraction:g}")
        painter.setPen(Qt.PenStyle.NoPen)
        for hour, minutes in enumerate(self.minutes):
            if minutes <= 0:
                continue
            height = max(1.5, plot.height()*minutes/maximum)
            rect = QRectF(plot.left()+hour*column+1.5, plot.bottom()-height, max(1, column-4), height)
            colour = QColor(accent)
            if hour == self._highlight_hour:
                t = self._highlight_opacity
                colour = QColor.fromRgbF(accent.redF()+(selected.redF()-accent.redF())*t,
                                        accent.greenF()+(selected.greenF()-accent.greenF())*t,
                                        accent.blueF()+(selected.blueF()-accent.blueF())*t)
            painter.setBrush(colour)
            painter.drawRoundedRect(rect, min(3, rect.width()/3), 3)
        painter.setPen(muted)
        for hour in (0, 6, 12, 18, 24):
            x = plot.left()+plot.width()*hour/24
            painter.drawText(QRectF(x-12, plot.bottom()+7, 26, 15), Qt.AlignmentFlag.AlignCenter, f"{hour:02d}")
        if self.hasFocus():
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(0, 42), QPointF(self.width(), 42))
        painter.end()

    def mouseMoveEvent(self, event):
        plot = self.plot_rect()
        hour = None
        if plot.contains(event.position()):
            hour = min(23, max(0, int((event.position().x()-plot.left()) / plot.width()*24)))
        self._set_hover(hour)

    def leaveEvent(self, event):
        self._set_hover(None)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self._clear_hover(immediate=True)
        super().hideEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self.hovered_hour is None:
                hour = next((hour for hour, value in enumerate(self.minutes) if value), 0)
            else:
                hour = min(23, max(0, self.hovered_hour + (1 if key == Qt.Key.Key_Right else -1)))
            self._set_hover(hour)
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            self._set_hover(0 if key == Qt.Key.Key_Home else 23)
        elif key == Qt.Key.Key_Escape:
            self._set_hover(None)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def focusOutEvent(self, event):
        self._set_hover(None)
        super().focusOutEvent(event)

    def event(self, event):
        # Clear an active hour before passing Escape to the window shortcut.
        if (event.type() == QEvent.Type.ShortcutOverride
                and event.key() == Qt.Key.Key_Escape
                and event.modifiers() == Qt.KeyboardModifier.NoModifier
                and self.hovered_hour is not None):
            event.accept()
            return True
        # Keep inspection in the inline readout instead of a native tooltip.
        if event.type() == QEvent.Type.ToolTip:
            return True
        return super().event(event)
