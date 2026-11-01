"""Book appearance and shelf-placement editor."""

from copy import copy, deepcopy
from pathlib import Path
import shutil
from uuid import uuid4

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from planner.books import TEMPLATES, _value
from .book_painting import draw_book


def _text(text, muted=False):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if muted:
        label.setObjectName("muted")
    return label


class BookPreview(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setMinimumSize(260, 300)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        night = bool(getattr(getattr(self.editor.parentWidget(), "scene", None), "night_mode", False))
        painter.fillRect(self.rect(), QColor("#233039" if night else "#E8E9DE"))
        draft = self.editor.current_draft()
        if draft is None:
            painter.end()
            return
        project = self.editor.projects_by_id[self.editor.project_combo.currentData()]
        appearance = deepcopy(draft["appearance"])
        for side, path in draft["pending"].items():
            appearance[side + "_image"] = str(path)
        title = appearance["title"] or _value(project, "title", "")

        def load_image(value):
            path = Path(value)
            reader = QImageReader(str(path if path.is_absolute() else self.editor.data_root / path))
            reader.setAutoTransform(True)
            size = reader.size()
            if size.width() > 768 or size.height() > 768:
                reader.setScaledSize(size.scaled(QSize(768, 768), Qt.AspectRatioMode.KeepAspectRatio))
            return QPixmap.fromImage(reader.read())

        top = max(32, (self.height() - 260) / 2)
        draw_book(painter, QRectF(30, top, 144, 220), appearance, title, "cover", load_image, 0)
        draw_book(painter, QRectF(204, top, 30, 220), appearance, title, "spine", load_image, 0)
        painter.setPen(QColor("#A7B49C" if night else "#7A8372"))
        painter.drawText(QRectF(30, top + 237, 144, 24), Qt.AlignmentFlag.AlignCenter, "COVER")
        painter.drawText(QRectF(183, top + 237, 72, 24), Qt.AlignmentFlag.AlignCenter, "SPINE")
        painter.end()


class ShelfMap(QWidget):
    selected = Signal(int)

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.setFixedHeight(72)
        self.setMinimumWidth(250)
        self.setToolTip("Click a cell to place the selected book. Sage cells show its current position.")

    def cell_rect(self, slot):
        return QRectF((slot % 10) * self.width() / 10 + 2, (slot // 10) * 24 + 2,
                      self.width() / 10 - 4, 20)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        occupied, selected = set(), set()
        night = bool(getattr(getattr(self.editor.parentWidget(), "scene", None), "night_mode", False))
        for entry in self.editor.preview_layout():
            if entry["slot"] is not None:
                cells = self.editor.book_service.cells(entry["slot"], entry["facing"])
                (selected if entry["id"] == self.editor.project_combo.currentData() else occupied).update(cells)
        for slot in range(30):
            painter.setBrush(QColor(("#81976F" if slot in selected else "#53624C" if slot in occupied else "#26332E") if night else ("#879B7C" if slot in selected else "#D3D9C9" if slot in occupied else "#F7F7EF")))
            painter.setPen(QPen(QColor("#64785B" if night else "#BDC7B2"), .7))
            painter.drawRoundedRect(self.cell_rect(slot), 3, 3)
            painter.setPen(QColor("#E1E9D5" if night else "#FAFBF4" if slot in selected else "#68765F"))
            painter.drawText(self.cell_rect(slot), Qt.AlignmentFlag.AlignCenter, str(slot % 10 + 1))
        painter.end()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            for slot in range(30):
                if self.cell_rect(slot).contains(event.position()):
                    self.selected.emit(slot)
                    break


class BookEditorDialog(QDialog):
    """Edit book drafts and save them together."""

    def __init__(self, book_service, projects, room_id, data_path, project_id=None, parent=None):
        super().__init__(parent)
        self.book_service = book_service
        self.projects = list(projects)
        self.projects_by_id = {_value(project, "id"): project for project in self.projects}
        self.room_id = room_id
        self.data_root = Path(data_path).parent
        self.drafts = {}
        self.dirty_ids = set()
        self._loading = True
        self._active_id = None
        self.setWindowTitle("Book design")
        self.resize(880, 650)
        self.setMinimumSize(780, 620)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)
        title = _text("Book design")
        title.setObjectName("dialogTitle")
        outer.addWidget(title)
        outer.addWidget(_text("Choose a cover, a spine and a place on the study shelf.", True))
        self.project_combo = QComboBox()
        for project in self.projects:
            pid = _value(project, "id")
            self.project_combo.addItem(_value(project, "title", "Untitled"), pid)
            self.drafts[pid] = {
                "appearance": book_service.appearance(pid, _value(project, "color", "#8FA79D")),
                **book_service.placement(pid, room_id), "pending": {},
            }
        outer.addWidget(self.project_combo)
        middle = QHBoxLayout()
        middle.setSpacing(24)
        self.preview = BookPreview(self)
        middle.addWidget(self.preview, 2)
        right = QVBoxLayout()
        right.setSpacing(10)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.template_combo = QComboBox()
        for key, template in TEMPLATES.items():
            self.template_combo.addItem(template["name"], key)
        form.addRow("Template", self.template_combo)
        self.title_edit = QLineEdit()
        self.title_edit.setMaxLength(200)
        self.title_edit.setPlaceholderText("Use the project title")
        self.title_edit.setToolTip("Printed on templates. An imported image replaces that side's entire printed design.")
        form.addRow("Template title", self.title_edit)
        colours = QHBoxLayout()
        self.cover_colour = QPushButton("Cover colour")
        self.spine_colour = QPushButton("Spine colour")
        colours.addWidget(self.cover_colour)
        colours.addWidget(self.spine_colour)
        form.addRow("Colours", colours)
        self.image_labels = {}
        for side in ("cover", "spine"):
            image_row = QHBoxLayout()
            choose = QPushButton("Choose image…")
            clear = QPushButton("Clear")
            choose.clicked.connect(lambda checked=False, s=side: self.choose_image(s))
            clear.clicked.connect(lambda checked=False, s=side: self.clear_image(s))
            image_row.addWidget(choose)
            image_row.addWidget(clear)
            form.addRow(side.title() + " image", image_row)
            self.image_labels[side] = choose
        self.facing_combo = QComboBox()
        self.facing_combo.addItem("Spine out · 1 space", "spine")
        self.facing_combo.addItem("Cover out · 3 spaces", "cover")
        form.addRow("Display", self.facing_combo)
        self.position_combo = QComboBox()
        self.position_combo.addItem("Automatic position", "auto")
        self.position_combo.addItem("Keep off the shelf", None)
        for slot in range(30):
            self.position_combo.addItem(f"{'Top' if slot < 10 else 'Middle' if slot < 20 else 'Bottom'} shelf · position {slot % 10 + 1}", slot)
        form.addRow("Position", self.position_combo)
        right.addLayout(form)
        self.shelf_map = ShelfMap(self)
        right.addWidget(self.shelf_map)
        right.addWidget(_text("Select a shelf position. A cover occupies three spaces; a spine occupies one. Automatic placement uses free spaces.", True))
        middle.addLayout(right, 3)
        outer.addLayout(middle, 1)
        self.error_label = _text("")
        self.error_label.setObjectName("error")
        self.error_label.hide()
        outer.addWidget(self.error_label)
        footer = QHBoxLayout()
        footer.addWidget(_text("Save applies all books edited in this window.", True), 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        self.save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setObjectName("primary")
        self.save_button.setEnabled(bool(self.projects))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        outer.addLayout(footer)
        # Fit the controls within the minimum dialog size.
        for widget in self.findChildren(QPushButton):
            widget.setMinimumHeight(30)
            widget.setStyleSheet("padding: 5px 9px;")
        for widget in (*self.findChildren(QComboBox), self.title_edit):
            widget.setStyleSheet("padding: 5px 8px; min-height: 18px;")
        self.project_combo.currentIndexChanged.connect(self.load_project)
        self.template_combo.currentIndexChanged.connect(self.change_template)
        self.title_edit.textChanged.connect(self.capture_current)
        self.facing_combo.currentIndexChanged.connect(self.capture_current)
        self.position_combo.currentIndexChanged.connect(self.capture_current)
        self.cover_colour.clicked.connect(lambda: self.choose_colour("cover"))
        self.spine_colour.clicked.connect(lambda: self.choose_colour("spine"))
        self.shelf_map.selected.connect(lambda slot: self.position_combo.setCurrentIndex(self.position_combo.findData(slot)))
        if project_id in self.projects_by_id:
            self.project_combo.setCurrentIndex(self.project_combo.findData(project_id))
        self.load_project()

    def current_draft(self):
        return self.drafts.get(self._active_id)

    def load_project(self, *args):
        self._loading = True
        self._active_id = self.project_combo.currentData()
        draft = self.current_draft()
        if draft:
            appearance = draft["appearance"]
            self.template_combo.setCurrentIndex(self.template_combo.findData(appearance["template"]))
            self.title_edit.setText(appearance["title"])
            self.facing_combo.setCurrentIndex(self.facing_combo.findData(draft["facing"]))
            self.position_combo.setCurrentIndex(self.position_combo.findData(draft["slot"]))
        self._loading = False
        self.refresh_preview()

    def capture_current(self, *args):
        if self._loading or self.current_draft() is None:
            return
        draft = self.current_draft()
        draft["appearance"]["title"] = self.title_edit.text().strip()
        draft["facing"] = self.facing_combo.currentData()
        draft["slot"] = self.position_combo.currentData()
        self.dirty_ids.add(self._active_id)
        self.refresh_preview()

    def change_template(self, *args):
        if self._loading or self.current_draft() is None:
            return
        appearance = self.current_draft()["appearance"]
        key = self.template_combo.currentData()
        appearance.update({"template": key, "cover_color": TEMPLATES[key]["cover_color"],
                           "spine_color": TEMPLATES[key]["spine_color"]})
        self.capture_current()

    def choose_colour(self, side):
        draft = self.current_draft()
        if draft is None:
            return
        colour = QColorDialog.getColor(QColor(draft["appearance"][side + "_color"]), self, side.title() + " colour")
        if colour.isValid():
            draft["appearance"][side + "_color"] = colour.name()
            self.capture_current()

    def choose_image(self, side):
        if self.current_draft() is None:
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Choose " + side + " artwork", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not filename:
            return
        try:
            source = Path(filename)
            self.validate_image(source)
            self.current_draft()["pending"][side] = source
            self.capture_current()
        except (OSError, ValueError) as exc:
            self.show_error(str(exc))

    @staticmethod
    def validate_image(source):
        if source.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("Choose an image no larger than 10 MB.")
        reader = QImageReader(str(source))
        size = reader.size()
        if not reader.canRead() or not size.isValid() or size.width() * size.height() > 25_000_000:
            raise ValueError("Choose a readable image smaller than 25 million pixels.")
        if reader.read().isNull():
            raise ValueError("This image could not be read.")

    def clear_image(self, side):
        draft = self.current_draft()
        if draft is not None:
            draft["pending"].pop(side, None)
            draft["appearance"][side + "_image"] = ""
            self.capture_current()

    def preview_layout(self):
        preview_service = copy(self.book_service)
        preview_service._state = self.book_service.snapshot()
        for pid, draft in self.drafts.items():
            preview_service._state["placements"][self.room_id][pid] = {"slot": draft["slot"], "facing": draft["facing"]}
        return preview_service.layout(self.room_id, self.projects)

    def refresh_preview(self):
        draft = self.current_draft()
        if draft:
            for side, widget in (("cover", self.cover_colour), ("spine", self.spine_colour)):
                widget.setStyleSheet("padding: 5px 9px; border: 2px solid " + draft["appearance"][side + "_color"] + ";")
                path = draft["pending"].get(side) or draft["appearance"][side + "_image"]
                name = Path(path).name if path else "Choose image…"
                self.image_labels[side].setText((name if len(name) < 22 else name[:12] + "…" + name[-6:]).replace("&", "&&"))
                self.image_labels[side].setToolTip(str(path) if path else "Use template artwork, or choose your own image.")
        self.error_label.hide()
        self.preview.update()
        self.shelf_map.update()

    def show_error(self, message):
        self.error_label.setText(message)
        self.error_label.show()

    def accept(self):
        if not self.projects:
            return
        copied, changes = [], []
        try:
            for pid in self.dirty_ids:
                draft = self.drafts[pid]
                appearance = deepcopy(draft["appearance"])
                for side, source in draft["pending"].items():
                    self.validate_image(source)
                    suffix = source.suffix.lower()
                    target = self.data_root / "book-images" / (uuid4().hex + suffix)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    copied.append(target)
                    shutil.copyfile(source, target)
                    appearance[side + "_image"] = target.relative_to(self.data_root).as_posix()
                changes.append({"id": pid, "appearance": appearance, "room_id": self.room_id,
                                "slot": draft["slot"], "facing": draft["facing"]})
            if changes:
                self.book_service.save_books(changes, self.projects)
        except (OSError, ValueError) as exc:
            for target in copied:
                target.unlink(missing_ok=True)
            self.show_error(str(exc))
            return
        super().accept()
