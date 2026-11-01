"""Personal-note editing and the home-page note display."""

from html import escape

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal, QSignalBlocker
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from planner.notes import MAX_EDIT_LENGTH, MAX_NOTES, validate_notes


def _label(text, role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


class RoomNoteWidget(QWidget):
    """Lay out a note in the room's serif typeface."""

    shuffle_requested = Signal()
    edit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.note = ""
        self.night_mode = False
        self.caption = "YOUR NOTE"
        self.font_size = 32
        self.display_text = ""
        self._actions_visible = True
        self._layout_cache = None
        self.shuffle_button = QPushButton("Another note", self)
        self.edit_button = QPushButton("Edit notes", self)
        for button in (self.shuffle_button, self.edit_button):
            button.setObjectName("ghost")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        self.shuffle_button.clicked.connect(lambda: self.shuffle_requested.emit())
        self.edit_button.clicked.connect(lambda: self.edit_requested.emit())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Your room note")
        self.set_note("")

    def sizeHint(self):
        return QSize(330, 230)

    def set_note(self, note):
        if not isinstance(note, str):
            raise ValueError("A room note must be text.")
        if note != self.note:
            self.note = note
            self._layout_cache = None
            self.update()
        self.shuffle_button.setEnabled(bool(note))
        self.setToolTip("<qt>" + escape(note).replace("\n", "<br>") + "</qt>" if note else "Add a thought to display in your study.")
        self.setAccessibleDescription(note or "Add a personal note")

    def set_night_mode(self, enabled):
        self.night_mode = bool(enabled)
        self.update()

    def set_actions_visible(self, visible):
        self._actions_visible = bool(visible)
        self.shuffle_button.setVisible(visible)
        self.edit_button.setVisible(visible)
        self._layout_cache = None
        self.update()

    def set_shuffle_enabled(self, enabled):
        self.shuffle_button.setEnabled(bool(enabled) and bool(self.note))

    def body_rect(self):
        bottom = 37 if self._actions_visible else 8
        return QRectF(12, 43, max(1, self.width() - 24), max(1, self.height() - 43 - bottom))

    @staticmethod
    def _text_layout(text, size, width):
        font = QFont()
        font.setFamilies(["Georgia", "Songti SC", "Noto Serif CJK SC", "serif"])
        font.setPixelSize(size)
        # QTextLayout needs an explicit line separator for user-entered newlines.
        layout = QTextLayout(text.replace("\n", "\u2028"), font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        y = 0.0
        count = 0
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            line.setPosition(QPointF(0, y))
            y += line.height() * 1.15
            count += 1
        layout.endLayout()
        return layout, y, count

    def _balanced_layout(self, text, size, width, height, initial, line_count):
        """Balance short notes without shrinking the font.
        Try narrower line widths but preserve explicit user line breaks."""
        if line_count not in (2, 3) or len(text) > 160 or "\n" in text or "\u2028" in text:
            return initial

        def score(layout, measure):
            lengths = [layout.lineAt(n).naturalTextWidth() for n in range(layout.lineCount())]
            average = sum(lengths) / len(lengths)
            if average <= 0:
                return float("inf")
            imbalance = sum((length - average) ** 2 for length in lengths) / (len(lengths) * average ** 2)
            # Prefer the wider measure if two candidates balance equally.
            return imbalance + .025 * (1 - measure / width)

        best, best_score = initial, score(initial, width)
        minimum = max(size * 4, int(width * .55))
        step = max(2, int(width / 100))
        for measure in range(minimum, int(width), step):
            candidate, candidate_height, lines = self._text_layout(text, size, measure)
            if lines != line_count or candidate_height > height:
                continue
            candidate_score = score(candidate, measure)
            if candidate_score < best_score:
                best, best_score = candidate, candidate_score
        return best

    def _fitted_layout(self):
        rect = self.body_rect()
        text = self.note or "Add a note for your study."
        key = (text, int(rect.width()), int(rect.height()))
        if self._layout_cache is not None and self._layout_cache[0] == key:
            return self._layout_cache[1]
        minimum = 23
        chosen = None
        for size in range(34, minimum - 1, -1):
            layout, height, lines = self._text_layout(text, size, rect.width())
            if height <= rect.height() and lines <= 5:
                chosen = self._balanced_layout(text, size, rect.width(), rect.height(), layout, lines)
                self.font_size = size
                self.display_text = text
                break
        if chosen is None:
            # Shorten only the display; the editor retains the complete note.
            lo, hi = 0, len(text)
            while lo < hi:
                middle = (lo + hi + 1) // 2
                candidate = text[:middle].rstrip() + "…"
                _, height, lines = self._text_layout(candidate, minimum, rect.width())
                if height <= rect.height() and lines <= 5:
                    lo = middle
                else:
                    hi = middle - 1
            self.display_text = text[:lo].rstrip() + "…"
            self.font_size = minimum
            chosen, _, _ = self._text_layout(self.display_text, minimum, rect.width())
        self._layout_cache = (key, chosen)
        return chosen

    def resizeEvent(self, event):
        self.shuffle_button.setGeometry(0, self.height() - 31, 98, 28)
        self.edit_button.setGeometry(108, self.height() - 31, 80, 28)
        self._layout_cache = None
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#64715F" if self.night_mode else "#ADB59F"), .8))
        painter.drawLine(0, 4, 42, 4)
        font = QFont("Avenir Next")
        font.setPixelSize(10)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.6)
        painter.setFont(font)
        painter.setPen(QColor("#A6B49A" if self.night_mode else "#7C8774"))
        painter.drawText(QRectF(0, 15, self.width(), 20), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.caption)
        painter.setPen(QColor("#D1DAC4" if self.night_mode else "#53614D"))
        painter.setClipRect(self.body_rect())
        self._fitted_layout().draw(painter, self.body_rect().topLeft())
        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.body_rect().contains(event.position()):
            self.edit_requested.emit()
        else:
            super().mouseReleaseEvent(event)


class NotesDialog(QDialog):
    """Edit note drafts; the main window saves the list."""

    def __init__(self, notes, parent=None):
        super().__init__(parent)
        self.notes = validate_notes(notes)
        self.original_notes = list(self.notes)
        self._loading = False
        self._active_row = -1
        self.setWindowTitle("Your notes")
        self.resize(760, 540)
        self.setMinimumSize(660, 470)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 20)
        outer.setSpacing(12)
        outer.addWidget(_label("Your notes", "dialogTitle"))
        outer.addWidget(_label("Add reminders or short notes. One appears on the Room page.", "muted"))
        middle = QHBoxLayout()
        middle.setSpacing(20)
        left = QVBoxLayout()
        self.note_list = QListWidget()
        self.note_list.setMinimumWidth(180)
        self.note_list.setMaximumWidth(220)
        self.note_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.note_list.setAccessibleName("Saved room notes")
        left.addWidget(self.note_list, 1)
        actions = QHBoxLayout()
        self.add_button = QPushButton("Add note")
        self.remove_button = QPushButton("Remove")
        actions.addWidget(self.add_button)
        actions.addWidget(self.remove_button)
        left.addLayout(actions)
        middle.addLayout(left, 2)
        right = QVBoxLayout()
        self.note_edit = QPlainTextEdit()
        self.editor = self.note_edit
        self.note_edit.setPlaceholderText("Write your note…")
        self.note_edit.setFixedHeight(118)
        self.note_edit.setAccessibleName("Note text")
        right.addWidget(self.note_edit)
        self.count_label = _label("", "muted")
        right.addWidget(self.count_label)
        self.preview = RoomNoteWidget()
        self.preview.caption = "IN YOUR STUDY"
        self.preview.set_actions_visible(False)
        self.preview.setMinimumHeight(170)
        self.preview.set_night_mode(bool(getattr(getattr(parent, "scene", None), "night_mode", False)))
        right.addWidget(self.preview, 1)
        middle.addLayout(right, 3)
        outer.addLayout(middle, 1)
        self.error_label = _label("", "error")
        self.error_label.hide()
        outer.addWidget(self.error_label)
        footer = QHBoxLayout()
        footer.addWidget(_label(f"Up to {MAX_NOTES} notes. New or edited notes: {MAX_EDIT_LENGTH} characters each.", "muted"), 1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setObjectName("primary")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        footer.addWidget(self.buttons)
        outer.addLayout(footer)
        self.add_button.clicked.connect(self.add_note)
        self.remove_button.clicked.connect(self.remove_note)
        self.note_list.currentRowChanged.connect(self._select_note)
        self.note_edit.textChanged.connect(self._changed)
        self._rebuild(0 if self.notes else -1)

    def _rebuild(self, selected):
        with QSignalBlocker(self.note_list):
            self.note_list.clear()
            for index, note in enumerate(self.notes):
                first = note.strip().splitlines()[0] if note.strip() else "New note"
                entry = QListWidgetItem(first)
                entry.setSizeHint(QSize(180, 45))
                self.note_list.addItem(entry)
            self.note_list.setCurrentRow(selected)
        self._select_note(selected)
        self.add_button.setEnabled(len(self.notes) < MAX_NOTES)

    def _select_note(self, row):
        self._active_row = row
        self._loading = True
        self.note_edit.setPlainText(self.notes[row] if 0 <= row < len(self.notes) else "")
        self._loading = False
        enabled = 0 <= row < len(self.notes)
        self.note_edit.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self._refresh()

    def _changed(self):
        if self._loading or not 0 <= self._active_row < len(self.notes):
            return
        text = self.note_edit.toPlainText()
        self.notes[self._active_row] = text
        first = text.strip().splitlines()[0] if text.strip() else "New note"
        self.note_list.item(self._active_row).setText(first)
        self._refresh()

    def _refresh(self):
        text = self.note_edit.toPlainText()
        legacy = text in self.original_notes and len(text) > MAX_EDIT_LENGTH
        self.count_label.setText(f"{len(text)} / {MAX_EDIT_LENGTH} characters" + (" · original note preserved" if legacy else ""))
        self.preview.set_note(text)
        self.error_label.hide()

    def add_note(self):
        if len(self.notes) >= MAX_NOTES:
            return
        self.notes.append("")
        self._rebuild(len(self.notes) - 1)
        self.note_edit.setFocus()

    def remove_note(self):
        row = self.note_list.currentRow()
        if not 0 <= row < len(self.notes):
            return
        del self.notes[row]
        self._rebuild(min(row, len(self.notes) - 1))

    def payload(self):
        cleaned = [text if text in self.original_notes and len(text) > MAX_EDIT_LENGTH else text.strip()
                   for text in self.notes]
        validate_notes(cleaned)
        for text in cleaned:
            if len(text) > MAX_EDIT_LENGTH and text not in self.original_notes:
                raise ValueError(f"New or edited notes must be at most {MAX_EDIT_LENGTH} characters.")
        return cleaned

    def accept(self):
        try:
            self.payload()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            return
        super().accept()
