"""Duration entry and date selection controls."""

from decimal import Decimal, InvalidOperation
import re

from PySide6.QtCore import QDate, QEvent, QObject, QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPalette, QTextCharFormat
from PySide6.QtWidgets import (
    QApplication, QCalendarWidget, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QSizePolicy, QTextEdit, QVBoxLayout, QWidget,
)


class _TextInputSupport(QObject):
    """Keep native editing cues clear over the illustrated room."""

    def eventFilter(self, widget, event):
        if event.type() not in (
                QEvent.Type.Polish, QEvent.Type.Show, QEvent.Type.FocusIn,
                QEvent.Type.StyleChange):
            return False
        if isinstance(widget, QLineEdit):
            widget.setCursor(Qt.CursorShape.IBeamCursor)
        elif isinstance(widget, (QTextEdit, QPlainTextEdit)):
            widget.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            widget.setCursorWidth(max(2, widget.cursorWidth()))
        else:
            return False
        if event.type() == QEvent.Type.FocusIn:
            widget.update()
        # Leave key events, selection, and input-method composition to Qt.
        return False


def install_text_input_support(application):
    """Install once; later dialogs and inline editors receive the same cues."""
    if not hasattr(application, "_anchor_text_input_support"):
        support = _TextInputSupport(application)
        application.installEventFilter(support)
        application._anchor_text_input_support = support


def parse_duration(text):
    """Return whole minutes from ``45``, ``1:30`` or ``1h 30m``."""
    text = text.strip().lower().replace(",", "")
    if re.fullmatch(r"\d+", text):
        return int(text)
    clock = re.fullmatch(r"(\d+):([0-5]\d)", text)
    if clock:
        return int(clock[1]) * 60 + int(clock[2])
    match = re.fullmatch(
        r"(?:(\d+(?:\.\d+)?)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?", text)
    if not match or not any(match.groups()):
        raise ValueError("Enter minutes, 1h 30m, or 1:30.")
    try:
        minutes = Decimal(match[1] or "0") * 60 + Decimal(match[2] or "0")
    except InvalidOperation as exc:
        raise ValueError("Enter a valid duration.") from exc
    if minutes != minutes.to_integral_value():
        raise ValueError("Use a duration containing whole minutes.")
    return int(minutes)


def format_duration(minutes):
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    return f"{hours}h" if hours else f"{rest}m"


class DurationInput(QWidget):
    """Accept typed durations and optional preset buttons."""

    valueChanged = Signal(int)

    def __init__(self, value=30, presets=(15, 25, 45, 60), parent=None):
        super().__init__(parent)
        self._minimum, self._maximum = 1, 10_000_000
        self._last_value = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.editor = QLineEdit()
        self.editor.setAccessibleName("Duration in minutes or hours")
        self.editor.setPlaceholderText("1h 30m")
        self.editor.setToolTip("Type minutes, 1h 30m, or 1:30. Presets are optional.")
        self.editor.setMinimumWidth(76)
        self.editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.editor, 1)
        self.preset_buttons = {}
        for minutes in presets:
            chip = QPushButton(format_duration(minutes))
            chip.setCheckable(True)
            chip.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            chip.setToolTip(f"Use {minutes} minutes")
            chip.setStyleSheet("padding: 6px 7px; min-height: 18px; font-size: 11px;")
            chip.clicked.connect(lambda checked=False, amount=minutes: self.setValue(amount))
            self.preset_buttons[minutes] = chip
            layout.addWidget(chip)
        self.setFocusProxy(self.editor)
        self.editor.textChanged.connect(self._text_changed)
        self.editor.editingFinished.connect(self._normalise)
        self.setValue(value)

    def _text_changed(self, text):
        try:
            amount = self.value()
        except ValueError:
            amount = None
        for value, chip in self.preset_buttons.items():
            chip.setChecked(value == amount)
        if amount is not None and amount != self._last_value:
            self._last_value = amount
            self.valueChanged.emit(amount)

    def _normalise(self):
        try:
            self.interpretText()
        except ValueError:
            # Keep invalid text so Save can report it to the user.
            return

    def value(self):
        amount = parse_duration(self.editor.text())
        if not self._minimum <= amount <= self._maximum:
            raise ValueError(f"Choose a duration from {self._minimum:,} to {self._maximum:,} minutes.")
        return amount

    def setValue(self, amount):
        if type(amount) is not int:
            raise ValueError("Duration must be a whole number of minutes.")
        amount = max(self._minimum, min(amount, self._maximum))
        self.editor.setText(format_duration(amount))

    def setRange(self, minimum, maximum):
        if type(minimum) is not int or type(maximum) is not int or minimum < 1 or maximum < minimum:
            raise ValueError("Invalid duration range.")
        previous = self._last_value if self._last_value is not None else minimum
        self._minimum, self._maximum = minimum, maximum
        self.setValue(previous)

    def minimum(self):
        return self._minimum

    def maximum(self):
        return self._maximum

    def lineEdit(self):
        return self.editor

    def interpretText(self):
        self.setValue(self.value())


def _night(widget):
    ancestor = widget
    dark_window = False
    while ancestor is not None:
        scene = getattr(ancestor, "scene", None)
        if scene is not None:
            return bool(getattr(scene, "night_mode", False))
        if ancestor.isWindow():
            dark_window = dark_window or ancestor.palette().color(QPalette.ColorRole.Window).lightness() < 110
        ancestor = ancestor.parentWidget()
    return dark_window or widget.palette().color(QPalette.ColorRole.Window).lightness() < 110


class _Calendar(QCalendarWidget):
    """Draw date cells while retaining Qt's keyboard controls."""

    def paintCell(self, painter, rect, on):
        popup = self.parentWidget()
        dark = popup.dark
        painter.save()
        selected = on == self.selectedDate()
        valid = self.minimumDate() <= on <= self.maximumDate()
        current_month = on.month() == self.monthShown()
        if selected and valid:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#9AAD8B" if dark else "#718479"))
            painter.drawRoundedRect(QRectF(rect).adjusted(3, 3, -3, -3), 8, 8)
        color = ("#223129" if dark else "#FAFBF4") if selected and valid else (
            "#DDE5D3" if dark else "#35443B")
        if not valid or not current_month:
            color = "#69766B" if dark else "#A6AEA0"
        painter.setPen(QColor(color))
        font = QFont("Avenir Next", 11)
        font.setWeight(QFont.Weight.DemiBold if selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(on.day()))
        if on == QDate.currentDate() and not selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#A8BD92" if dark else "#718479"))
            painter.drawEllipse(QRectF(rect.center().x() - 1.5, rect.bottom() - 6, 3, 3))
        painter.restore()


class _DatePopup(QFrame):
    def __init__(self, owner):
        super().__init__(owner, Qt.WindowType.Popup)
        self.owner = owner
        self.dark = _night(owner)
        self.setObjectName("datePopup")
        surface = "#29343D" if self.dark else "#F8F6EF"
        ink = "#DDE5D3" if self.dark else "#35443B"
        border = "#52604F" if self.dark else "#D7DCCE"
        muted = "#A3B195" if self.dark else "#7C8773"
        self.setStyleSheet(f"""
QFrame#datePopup {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QCalendarWidget, QCalendarWidget QWidget {{ background: {surface}; color: {ink}; }}
QCalendarWidget QAbstractItemView {{ background: {surface}; color: {ink}; outline: 0; selection-background-color: transparent; border: none; }}
QCalendarWidget QHeaderView::section {{ background: {surface}; color: {muted}; border: none; }}
QPushButton {{ padding: 6px 9px; min-height: 20px; }}
QPushButton#calendarArrow {{ border: none; background: transparent; color: {ink}; font-size: 22px; padding: 0; }}
QLabel#calendarMonth {{ font-family: Georgia; font-size: 18px; color: {ink}; background: transparent; }}
""")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        self.previous = QPushButton("‹")
        self.next = QPushButton("›")
        for button, tip in ((self.previous, "Previous month"), (self.next, "Next month")):
            button.setObjectName("calendarArrow")
            button.setFixedWidth(30)
            button.setToolTip(tip)
        self.month_label = QLabel()
        self.month_label.setObjectName("calendarMonth")
        self.month_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self.previous)
        header.addWidget(self.month_label, 1)
        header.addWidget(self.next)
        layout.addLayout(header)
        self.calendar = _Calendar(self)
        self.calendar.setNavigationBarVisible(False)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setGridVisible(False)
        weekday_style = QTextCharFormat()
        weekday_style.setForeground(QColor(muted))
        for weekday in (Qt.DayOfWeek.Monday, Qt.DayOfWeek.Tuesday, Qt.DayOfWeek.Wednesday,
                        Qt.DayOfWeek.Thursday, Qt.DayOfWeek.Friday, Qt.DayOfWeek.Saturday,
                        Qt.DayOfWeek.Sunday):
            self.calendar.setWeekdayTextFormat(weekday, weekday_style)
        self.calendar.setDateRange(owner.minimumDate(), owner.maximumDate())
        self.calendar.setSelectedDate(owner.date())
        self.calendar.setCurrentPage(owner.date().year(), owner.date().month())
        self.calendar.setFixedSize(308, 246)
        layout.addWidget(self.calendar)
        quick = QHBoxLayout()
        quick.setSpacing(5)
        self.quick_buttons = {}
        today = QDate.currentDate()
        for title, on in (("Today", today), ("Tomorrow", today.addDays(1)),
                          ("+1 week", today.addDays(7)), ("+1 month", today.addMonths(1))):
            button = QPushButton(title)
            button.setStyleSheet("padding: 6px 5px; font-size: 10px;")
            button.setEnabled(owner.minimumDate() <= on <= owner.maximumDate())
            button.clicked.connect(lambda checked=False, selected=on: self.choose(selected))
            quick.addWidget(button)
            self.quick_buttons[title] = button
        layout.addLayout(quick)
        self.previous.clicked.connect(self.calendar.showPreviousMonth)
        self.next.clicked.connect(self.calendar.showNextMonth)
        self.calendar.currentPageChanged.connect(self._month_changed)
        self.calendar.clicked.connect(self.choose)
        self.calendar.activated.connect(self.choose)
        self._month_changed(self.calendar.yearShown(), self.calendar.monthShown())

    def _month_changed(self, year, month):
        self.month_label.setText(QDate(year, month, 1).toString("MMMM yyyy"))
        beginning = QDate(year, month, 1)
        ending = QDate(year, month, beginning.daysInMonth())
        self.previous.setEnabled(self.owner.minimumDate() < beginning)
        self.next.setEnabled(self.owner.maximumDate() > ending)

    def choose(self, on):
        if self.owner.minimumDate() <= on <= self.owner.maximumDate():
            self.owner.setDate(on)
            self.close()


class DateInput(QWidget):
    """Open a calendar from a compact date button."""

    dateChanged = Signal(QDate)

    def __init__(self, value=None, parent=None):
        super().__init__(parent)
        self._minimum, self._maximum = QDate(1752, 9, 14), QDate(9999, 12, 31)
        self._date = value or QDate.currentDate()
        self._format = "dd MMM yyyy"
        self.popup = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QPushButton()
        self.button.setAccessibleName("Choose date")
        self.button.setMinimumWidth(136)
        self.button.setStyleSheet("text-align: left; padding: 8px 10px;")
        self.button.clicked.connect(self.open_calendar)
        layout.addWidget(self.button)
        self.setFocusProxy(self.button)
        self._caption()

    def _caption(self):
        self.button.setText(self._date.toString(self._format) + "  ▾")

    def date(self):
        return QDate(self._date)

    def setDate(self, on):
        if not isinstance(on, QDate) or not on.isValid():
            raise ValueError("Choose a valid calendar date.")
        on = max(self._minimum, min(on, self._maximum))
        changed = on != self._date
        self._date = QDate(on)
        self._caption()
        if changed:
            self.dateChanged.emit(QDate(on))

    def minimumDate(self):
        return QDate(self._minimum)

    def maximumDate(self):
        return QDate(self._maximum)

    def setMinimumDate(self, on):
        if not isinstance(on, QDate) or not on.isValid():
            raise ValueError("Choose a valid minimum date.")
        self._minimum = QDate(on)
        if self._maximum < on:
            self._maximum = QDate(on)
        self.setDate(self._date)

    def setMaximumDate(self, on):
        if not isinstance(on, QDate) or not on.isValid():
            raise ValueError("Choose a valid maximum date.")
        self._maximum = QDate(on)
        if self._minimum > on:
            self._minimum = QDate(on)
        self.setDate(self._date)

    def setDisplayFormat(self, value):
        self._format = value
        self._caption()

    def interpretText(self):
        return None

    def open_calendar(self):
        if self.popup is not None:
            self.popup.close()
            self.popup.deleteLater()
        self.popup = _DatePopup(self)
        self.popup.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 6))
        screen = QApplication.screenAt(pos) or self.screen()
        bounds = screen.availableGeometry()
        x = max(bounds.left(), min(pos.x(), bounds.right() - self.popup.width() + 1))
        y = pos.y()
        if y + self.popup.height() > bounds.bottom():
            y = self.mapToGlobal(QPoint(0, 0)).y() - self.popup.height() - 6
        self.popup.move(x, max(bounds.top(), y))
        self.popup.show()
        self.popup.calendar.setFocus()
