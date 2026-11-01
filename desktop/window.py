"""Main window, page navigation and calls to the planner service."""

import math
import shutil
from datetime import date
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, QRectF, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImageReader, QKeySequence, QLinearGradient, QPainter, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
    QLabel, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QTabWidget, QToolTip, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from planner import FocusTimer, JsonRepository
from planner.activity import ActivityCapture
from planner.books import BookService
from planner.planning import recovery_summary
from planner.notes import normalize_notes, select_next_note
from .book_editor import BookEditorDialog
from .book_painting import draw_book
from .dialogs import NoteDialog, ProjectDialog, WorkLogDialog
from .daily_plan import build_daily_plan, build_recovery_card
from .music import MusicSession, build_music
from .notes import NotesDialog, RoomNoteWidget
from .notebook import build_notebook
from .record_stats import RecordStatsPanel
from .scene import RoomScene
from .theme import NIGHT_STYLE, STYLE


def label(text, role=None, wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        item.setObjectName(role)
    item.setWordWrap(wrap)
    return item


def button(text, action, role=None):
    item = QPushButton(text)
    if role:
        item.setObjectName(role)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    # Qt passes a checked flag, but these actions do not take it as an argument.
    item.clicked.connect(lambda checked=False: action())
    return item


def fit_combo(widget):
    """Keep long project names within the available panel width."""
    widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    widget.setMinimumContentsLength(12)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


def row(*items):
    layout = QHBoxLayout()
    layout.setSpacing(8)
    for item in items:
        layout.addWidget(item)
    return layout


def duration(minutes):
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}m" if rest else f"{hours}h"


class EffortBar(QWidget):
    """Display recorded time against a project or daily target."""
    def __init__(self, actual, planned, color, parent=None, *, caption="TIME INVESTED", lifetime=None):
        super().__init__(parent)
        self.actual, self.planned, self.color = actual, planned, color
        self.caption, self.lifetime = caption, lifetime
        self.setFixedHeight(126 if lifetime is not None else 108)
        self.setAccessibleName(f"Recorded effort {actual} minutes; reference target {planned} minutes")
        self.setToolTip("Recorded time compared with the original estimate. The outcome is confirmed separately." if lifetime is None else "Today's recorded time compared with your daily rhythm. Lifetime effort is preserved.")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        night = bool(getattr(getattr(self.window(), "scene", None), "night_mode", False))
        ink = QColor("#DCE5D2" if night else "#35483C")
        muted = QColor("#A6B39C" if night else "#788475")
        width = max(1, self.width() - 4)
        p.setPen(muted)
        p.setFont(QFont("Avenir Next", 9))
        p.drawText(QRectF(2, 0, width, 18), Qt.AlignmentFlag.AlignLeft, self.caption)
        p.setPen(ink)
        p.setFont(QFont("Avenir Next", 25))
        p.drawText(QRectF(0, 20, width, 38), Qt.AlignmentFlag.AlignLeft, duration(self.actual))
        ratio = min(self.actual / max(self.planned, 1), 1)
        track = QRectF(2, 65, width, 10)
        p.setPen(QPen(QColor("#53624B" if night else "#D5DDCE"), .7))
        p.setBrush(QColor("#3A493D" if night else "#E2E8DC"))
        p.drawRoundedRect(track, 5, 5)
        if ratio > 0:
            fill = QRectF(track.left(), track.top(), max(2, track.width()*ratio), track.height())
            gradient = QLinearGradient(fill.topLeft(), fill.topRight())
            accent = QColor(self.color)
            gradient.setColorAt(0, accent.lighter(120 if night else 112))
            gradient.setColorAt(1, accent.darker(103))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(gradient)
            p.drawRoundedRect(fill, 5, 5)
        p.setPen(muted)
        p.setFont(QFont("Avenir Next", 10))
        reference = "daily goal" if self.lifetime is not None else "original estimate"
        p.drawText(QRectF(2, 85, width, 18), Qt.AlignmentFlag.AlignLeft, f"of {duration(self.planned)} {reference}")
        if self.lifetime is not None:
            p.drawText(QRectF(2, 106, width, 18), Qt.AlignmentFlag.AlignLeft, f"{duration(self.lifetime)} recorded in total")
        p.end()


class AnchorWindow(QMainWindow):
    VIEWS = {
        "room": ("Room", "01 / THE WHOLE ROOM"),
        "plan": ("Notebook", "02 / AT THE BOOKSHELF"),
        "focus": ("Focus", "03 / AT THE DESK"),
        "collection": ("Collection", "04 / THE READING CORNER"),
        "music": ("Music", "05 / THE LISTENING CORNER"),
    }
    # Existing book positions are stored under this layout key.
    BOOK_LAYOUT_ID = "city"

    def __init__(self, service, data_path: Path, asset_path: Path, preview=False):
        super().__init__()
        self.service, self.data_path, self.preview = service, Path(data_path), preview
        self.book_service = BookService(JsonRepository(self.data_path.with_name("books.json")))
        self.immersive = False
        self.timer = FocusTimer()
        self.activity = ActivityCapture()
        self.session_project_id = None
        self.session_task_id = None
        self.session_date = None
        self.current_page = "room"
        self.selected_project_id = None
        self.panel = None
        self.clock_label = None
        self._plan_tabs_index = 0
        self._refreshing = False
        self.settings_repository = JsonRepository(self.data_path.with_name("room-settings.json"))
        self.settings_error = None
        try:
            self.settings = self.settings_repository.load()
            if not isinstance(self.settings.get("note", ""), str):
                raise ValueError("The saved room note must be text.")
            self.notes = normalize_notes(self.settings)
        except (ValueError, OSError) as exc:
            self.settings = {"schema_version": 1}
            self.settings_error = str(exc)
            self.notes = []
        self.current_note = select_next_note(self.notes)
        self.setWindowTitle("Anchor — The illustrated study" + (" [PREVIEW]" if preview else ""))
        self.setMinimumSize(1000, 700)
        self.resize(1440, 900)
        self.setStyleSheet(STYLE)
        self.scene = RoomScene(asset_path)
        self.scene.data_root = self.data_path.parent
        self.setCentralWidget(self.scene)
        self.scene.action_requested.connect(self.handle_scene_action)
        self.scene.set_motion(self.settings.get("motion", True) is True)
        self.scene.set_night_mode(self.settings.get("night_mode", False) is True)
        self.music_session = MusicSession(self)
        self.music_session.playback_changed.connect(self.scene.set_music_playing)
        self.music_session.status_changed.connect(self._observe_focus_music)
        self.music_session.reset.connect(self._clear_focus_music)
        self.music_session.failed.connect(lambda message: self._clear_focus_music())
        self._build_chrome()
        self._build_home()
        self._apply_color_mode()
        self.tick = QTimer(self)
        self.tick.setInterval(250)
        self.tick.timeout.connect(self.update_clock)
        self.tick.start()
        self.last_date = date.today()
        QShortcut(QKeySequence("Escape"), self, activated=self.escape)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_project)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.show_page("room"))
        QShortcut(QKeySequence("Ctrl+2"), self, activated=lambda: self.show_page("plan"))
        QShortcut(QKeySequence("Ctrl+3"), self, activated=lambda: self.show_page("focus"))
        QShortcut(QKeySequence("Ctrl+4"), self, activated=lambda: self.show_page("collection"))
        QShortcut(QKeySequence("Ctrl+5"), self, activated=lambda: self.show_page("music"))
        QShortcut(QKeySequence("Ctrl+I"), self, activated=self.toggle_immersion)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=self.edit_books)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        self.show_page("room")
        if self.settings_error:
            QTimer.singleShot(100, lambda: self.error("Room settings could not be read. The original file is preserved.\n" + self.settings_error))

    def _build_chrome(self):
        self.header = QWidget(self.scene)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(18)
        brand = label("anchor")
        self.brand_label = brand
        brand.setStyleSheet("font-family: Georgia; font-size: 29px; color: #35413B;")
        header.addWidget(brand)
        self.date_label = label(date.today().strftime("%A, %d %B"), "muted")
        header.addWidget(self.date_label)
        header.addStretch()
        self.session_chip = button("", lambda: self.show_page("focus"), "ghost")
        self.session_chip.hide()
        header.addWidget(self.session_chip)
        self.night_button = button("", self.toggle_night_mode, "ghost")
        self.night_button.setCheckable(True)
        self.night_button.setToolTip("Switch this same study between day and night")
        header.addWidget(self.night_button)
        self.immerse_button = button("Hide interface", self.toggle_immersion, "ghost")
        self.immerse_button.setToolTip("Ctrl+I · Esc or double-click to return")
        header.addWidget(self.immerse_button)
        self.options_button = button("···", lambda: None, "ghost")
        self.options_button.setAccessibleName("Room options")
        self.options_button.setToolTip("Note, animation, help and full screen")
        self.options_button.setFixedWidth(48)
        options = QMenu(self.options_button)
        options.addAction("Your notes", self.edit_room_note)
        self.motion_button = options.addAction("", self.toggle_motion)
        self._motion_caption()
        self.fullscreen_button = options.addAction("Full screen", self.toggle_fullscreen)
        options.addSeparator()
        options.addAction("Help and shortcuts", self.show_help)
        self.options_button.setMenu(options)
        header.addWidget(self.options_button)
        self.footer_surface = QFrame(self.scene)
        self.footer_surface.setStyleSheet("background: #EEEAE1;")
        self.footer_rule = QFrame(self.scene)
        self.footer_rule.setStyleSheet("background: #CBCFC1;")
        self.nav = QFrame(self.scene)
        self.nav.setObjectName("nav")
        nav_layout = QHBoxLayout(self.nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)
        self.nav_buttons = {}
        for index, (key, (title, caption)) in enumerate(self.VIEWS.items(), 1):
            b = button(title, lambda k=key: self.show_page(k), "navButton")
            b.setCheckable(True)
            b.setToolTip(caption.split(" / ")[1].title() + f" · Ctrl+{index}")
            self.nav_buttons[key] = b
            nav_layout.addWidget(b, 1)
        self.view_caption = label("", "eyebrow")
        self.view_caption.setParent(self.scene)
        self.local_label = label("PREVIEW · temporary data" if self.preview else "SAVED ON THIS COMPUTER", "muted")
        self.local_label.setParent(self.scene)
        self.local_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.local_label.setStyleSheet("font-size: 10px; color: #788074;")
        self.toast = label("")
        self.toast.setParent(self.scene)
        self.toast.setStyleSheet("background: #E5E9DE; color: #35413B; border: 1px solid #BEC8B9; border-radius: 5px; padding: 10px 14px;")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast.hide)

    def _build_home(self):
        self.hero = QWidget(self.scene)
        hero = QVBoxLayout(self.hero)
        hero.setContentsMargins(0, 0, 0, 0)
        hero.setSpacing(12)
        hero.addWidget(label("YOUR WORKSPACE", "eyebrow"))
        self.hero_title = label("The study")
        self.hero_title.setStyleSheet("font-family: Georgia; font-size: 44px; color: #35413B;")
        hero.addWidget(self.hero_title)
        self.room_status = label("", "muted", True)
        hero.addWidget(self.room_status)
        self.home_summary = label("", "muted", True)
        hero.addWidget(self.home_summary)
        self.today_total = label("", "section")
        effort = QHBoxLayout()
        effort.setSpacing(8)
        effort.addWidget(self.today_total)
        effort.addWidget(label("recorded today", "muted"))
        effort.addStretch()
        hero.addLayout(effort)
        hero.addSpacing(4)
        self.home_action = button("Open notebook  →", lambda: self.show_page("plan"), "primary")
        hero.addWidget(self.home_action, alignment=Qt.AlignmentFlag.AlignLeft)
        hero.addStretch()
        # Retain the settings label for compatibility with saved notes.
        self.note_label = label("")
        self.note_label.setParent(self.scene)
        self.note_label.hide()
        self.room_note = RoomNoteWidget(self.scene)
        self.room_note.set_note(self.current_note)
        self.room_note.set_shuffle_enabled(len(set(self.notes)) > 1)
        self.room_note.shuffle_requested.connect(self.shuffle_room_note)
        self.room_note.edit_requested.connect(self.edit_room_note)
        self.refresh_home()

    def refresh_home(self):
        projects = self.service.list_projects()
        total = sum(log.minutes for project in projects for log in project.logs if log.worked_on == date.today())
        active = sum(project.archived_at is None for project in projects)
        archived = len(projects) - active
        self.today_total.setText(duration(total))
        self.home_summary.setText(f"{active} active project{'s' if active != 1 else ''}  ·  {archived} archived")
        self.note_label.setText(self.current_note)
        self.hero_title.setText("The study")
        current = next((p for p in projects if p.id == self.selected_project_id and p.archived_at is None),
                       next((p for p in projects if p.archived_at is None), None))
        if current:
            recovery = recovery_summary(current, self.service.today())
            if recovery["status"] == "gentle_adjustment":
                self.room_status.setText(f"Today: {recovery['today_baseline_minutes']} min usual + {recovery['today_catch_up_minutes']} min catch-up.\n{recovery['today_additional_minutes']} min left to record.")
            elif recovery["capacity_pressure"]:
                self.room_status.setText("The remaining work does not fit this plan.\nReview the deadline or daily pace in Notebook.")
            else:
                self.room_status.setText(f"Today's suggestion: {recovery['today_additional_minutes']} more min.\n{current.title[:52]}")
        else:
            self.room_status.setText("Create a project to get started.\nYour projects will appear on the bookshelf.")
        book_layout = {entry["id"]: entry for entry in self.book_service.layout(self.BOOK_LAYOUT_ID, projects)}
        self.scene.configure(None, [{
            "id": project.id, "title": project.title, "color": project.color,
            "actual": sum(log.minutes for log in project.logs), "planned": project.planned_minutes,
            "archived": project.archived_at is not None,
            "book_slot": book_layout[project.id]["slot"],
            "book_facing": book_layout[project.id]["facing"],
            "book_appearance": book_layout[project.id]["appearance"],
        } for project in projects])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "header"):
            self.position_widgets()

    def position_widgets(self):
        w, h = self.scene.width(), self.scene.height()
        self.header.setGeometry(44, 24, w - 88, 48)
        self.hero.setGeometry(48, 122, 330, 270)
        note_y = 410 if h < 820 else 430
        self.room_note.setGeometry(48, note_y, min(330, w // 3), min(260, max(140, h - 118 - note_y)))
        self.footer_surface.setGeometry(0, h - 104, w, 104)
        self.footer_rule.setGeometry(44, h - 92, w - 88, 1)
        nav_width = 620
        self.nav.setGeometry((w - nav_width) // 2, h - 77, nav_width, 48)
        self.view_caption.setGeometry(48, h - 64, 250, 24)
        self.local_label.setGeometry(w - 268, h - 64, 220, 24)
        self.date_label.setVisible(w >= 1100)
        if self.panel:
            width = {"plan": min(850, max(700, int(w * .61))), "collection": 460, "focus": 390, "music": 460}.get(self.current_page, 460)
            self.panel.setGeometry(44, 96 if self.current_page == "plan" else 110, width, h - (208 if self.current_page == "plan" else 224))
        offset = max(0, self.panel.geometry().right() + 30 - w * .62) if self.panel and self.current_page == "plan" else 0
        self.scene.set_view_offset(offset)
        if self.current_page == "plan" and getattr(self, "notebook_motivation", None) is not None:
            self.notebook_motivation.setVisible(h >= 820)
        self.toast.setGeometry((w - 600) // 2, h - 144, 600, 42)
        self.header.raise_()
        self.nav.raise_()
        self.toast.raise_()
        self._apply_view_visibility()

    def notify(self, message):
        self.toast.setText(message)
        self.toast.setVisible(not self.immersive)
        self.toast.raise_()
        self.toast_timer.start(4200)

    def error(self, message):
        QMessageBox.warning(self, "Couldn't complete that action", str(message))

    def operate(self, action, message=None):
        try:
            action()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.error(exc)
            # Restore the saved checkbox state if writing fails.
            self.refresh_home()
            self.show_page(self.current_page)
            return False
        self.refresh_home()
        self.show_page(self.current_page)
        if message:
            self.notify(message)
        return True

    def show_page(self, name):
        if name in ("outside", "immersive"):
            self.show_page("room")
            self.enter_immersion(outdoor=name == "outside")
            return
        # Redirect obsolete page names to Room.
        if name not in self.VIEWS:
            name = "room"
        previous_page = self.current_page
        self.immersive = False
        self.scene.immersive = False
        self.scene.outdoor = False
        self.current_page = name
        if name == "room" and previous_page != "room":
            self.shuffle_room_note()
        self.scene.set_view(name)
        self.clock_label = None
        if self.panel:
            self.panel.hide()
            self.panel.deleteLater()
            self.panel = None
        for key, b in self.nav_buttons.items():
            b.setChecked(key == name)
        self.view_caption.setText(self.VIEWS[name][1])
        if name == "plan":
            self.build_plan()
        elif name == "focus":
            self.build_focus()
        elif name == "collection":
            self.build_collection()
        elif name == "music":
            build_music(self)
        self.position_widgets()
        self.scene.update()
        self._apply_color_mode(repolish=False)
        self.update_clock()

    def handle_scene_action(self, action):
        if action == "outside":
            self.enter_immersion(outdoor=True)
        elif action == "leave-immersion":
            self.leave_immersion()
        elif action.startswith("project:"):
            project = self.service.get_project(action.split(":", 1)[1])
            self.selected_project_id = project.id
            self.show_page("collection" if project.archived_at else "plan")
        elif action in self.VIEWS:
            self.show_page(action)

    def _apply_view_visibility(self):
        """Apply the current page and immersion visibility rules."""
        visible = not self.immersive
        self.header.setVisible(visible)
        self.nav.setVisible(visible)
        self.footer_surface.setVisible(visible)
        self.footer_rule.setVisible(visible)
        self.view_caption.setVisible(visible and self.scene.width() >= 1250)
        self.local_label.setVisible(visible and self.scene.width() >= 1350)
        self.hero.setVisible(visible and self.current_page == "room")
        self.room_note.setVisible(visible and self.current_page == "room")
        self.note_label.hide()
        if self.panel:
            self.panel.setVisible(visible)
        if not visible:
            self.toast.hide()
        self.scene.hotspots_visible = visible
        self.scene.configuration_mode = False
        self.scene.ui_exclusions = [QRectF(self.panel.geometry())] if visible and self.panel else []

    def enter_immersion(self, outdoor=False):
        self.immersive = True
        self.scene.immersive = True
        self.scene.outdoor = outdoor
        self.scene.hovered = None
        self.scene.setToolTip("")
        QToolTip.hideText()
        self.scene.setCursor(Qt.CursorShape.ArrowCursor)
        self._apply_view_visibility()
        self.scene.setFocus()
        self.scene.update()

    def leave_immersion(self):
        self.immersive = False
        self.scene.immersive = False
        self.scene.outdoor = False
        self._apply_view_visibility()
        self.scene.update()

    def toggle_immersion(self):
        self.leave_immersion() if self.immersive else self.enter_immersion()

    def edit_books(self, project_id=None):
        self.leave_immersion()
        projects = self.service.list_projects()
        if not projects:
            self.notify("Create a project in your notebook to give it a book.")
            return
        dialog = BookEditorDialog(self.book_service, projects, self.BOOK_LAYOUT_ID,
                                  self.data_path, project_id=project_id or self.selected_project_id,
                                  parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh_home()
            self.notify("Book design and shelf position saved.")

    def make_panel(self, title, subtitle, flat=False):
        self.panel = QFrame(self.scene)
        self.panel.setObjectName("panel")
        outer = QVBoxLayout(self.panel)
        outer.setContentsMargins(20, 18, 20, 18) if flat else outer.setContentsMargins(24, 22, 24, 20)
        outer.setSpacing(10)
        heading = QHBoxLayout()
        heading.addWidget(label(title, "title"))
        heading.addStretch()
        close = button("×", lambda: self.show_page("room"), "ghost")
        close.setToolTip("Return to the room (Esc)")
        close.setFixedWidth(36)
        heading.addWidget(close)
        outer.addLayout(heading)
        if subtitle:
            outer.addWidget(label(subtitle, "muted", True))
        if flat:
            content = QVBoxLayout()
            content.setContentsMargins(0, 0, 0, 0)
            content.setSpacing(10)
            outer.addLayout(content, 1)
            return content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(0, 8, 7, 0)
        content.setSpacing(12)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        return content

    def selected_project(self):
        if self.selected_project_id:
            return self.service.get_project(self.selected_project_id)
        return None

    def build_plan(self):
        build_notebook(self)

    def _plan_tab_changed(self, index):
        self._plan_tabs_index = index
        self.notebook_summary.setVisible(index != 2)
        summary = self.recovery_card.summary
        self.recovery_card.setVisible(index != 1 and bool(summary["has_adjustment"] or summary["capacity_pressure"]))

    def select_project(self):
        self.selected_project_id = self.project_combo.currentData()
        self.show_page("plan")

    def new_project(self):
        dialog = ProjectDialog(projects=self.service.list_projects(), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            def create():
                p = self.service.create_project(**dialog.payload())
                self.selected_project_id = p.id
            self.current_page = "plan"
            self._plan_tabs_index = 0
            self._task_page = 0
            self.operate(create, "A new page, ready for you.")

    def edit_project(self):
        p = self.selected_project()
        dialog = ProjectDialog(p, self.service.list_projects(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.operate(lambda: self.service.update_project(p.id, **dialog.payload()), "Project saved.")

    def import_picture(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose a project picture", "", "Pictures (*.png *.jpg *.jpeg *.webp)")
        if not filename:
            return
        target = None
        try:
            source = Path(filename)
            if source.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Please choose a picture smaller than 10 MB.")
            reader = QImageReader(str(source))
            size = reader.size()
            if not reader.canRead() or size.width() * size.height() > 25_000_000:
                raise ValueError("Choose a readable picture with at most 25 million pixels.")
            relative = Path("images") / (str(uuid4()) + source.suffix.lower())
            target = self.data_path.parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            self.service.update_project(self.selected_project_id, image_path=relative.as_posix())
        except (ValueError, OSError) as exc:
            if target and target.exists():
                target.unlink()
            self.error(exc)
            return
        self.show_page("plan")
        self.notify("Picture copied into your local collection.")

    def selected_task_id(self):
        item = self.task_tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item else None

    def add_task(self, parent_id=None):
        title, accepted = QInputDialog.getText(self, "A small next step", "Task name")
        if accepted:
            created = []
            def create():
                created.append(self.service.add_task(self.selected_project_id, title.strip(), parent_id))
            if self.operate(create):
                self.task_pages.select_task(created[0].id)

    def add_subtask(self):
        tid = self.selected_task_id()
        if not tid:
            self.notify("Select a task to break it into smaller steps.")
            return
        if self.task_tree.currentItem().parent() is not None:
            self.notify("Select a top-level task to add a subtask. Subtasks cannot contain another level.")
            return
        self.add_task(tid)

    def rename_task(self):
        tid = self.selected_task_id()
        if not tid:
            self.notify("Select a task first.")
            return
        current = self.selected_project().find_task(tid)
        title, accepted = QInputDialog.getText(self, "Rename task", "Task name", text=current.title)
        if accepted:
            self.operate(lambda: self.service.rename_task(self.selected_project_id, tid, title.strip()))

    def delete_task(self):
        tid = self.selected_task_id()
        if not tid:
            self.notify("Select a task first.")
            return
        if self.timer.state != "idle" and self.session_project_id == self.selected_project_id:
            self.notify("Finish the current focus session before deleting tasks here.")
            return
        if QMessageBox.question(self, "Delete this task?", "This removes the task and its smaller steps. Recorded time is kept with the project.") == QMessageBox.StandardButton.Yes:
            self.operate(lambda: self.service.delete_task(self.selected_project_id, tid), "Task removed; your time is preserved.")

    def toggle_task(self, item, column):
        if column != 0 or item.data(0, Qt.ItemDataRole.UserRole + 1):
            return
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        completed = item.checkState(0) == Qt.CheckState.Checked
        node = self.selected_project().find_task(tid)
        if node is None or node.completed == completed:
            return
        failure = None
        try:
            self.service.set_task_completed(self.selected_project_id, tid, completed)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            failure = exc
        project = self.service.get_project(self.selected_project_id)
        # Update in place to preserve the selected task and tree position.
        with QSignalBlocker(self.task_tree):
            node = project.find_task(tid)
            item.setCheckState(0, Qt.CheckState.Checked if node.completed else Qt.CheckState.Unchecked)
            ancestor = item.parent()
            while ancestor is not None:
                parent_node = project.find_task(ancestor.data(0, Qt.ItemDataRole.UserRole))
                text = ("✓  " if parent_node.is_complete() else "◦  ") + parent_node.title
                if ancestor.text(0) != text:
                    ancestor.setText(0, text)
                ancestor = ancestor.parent()
        if failure is not None:
            self.error(failure)

    def toggle_outcome(self, checked):
        try:
            self.service.update_project(self.selected_project_id, outcome_completed=checked)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            project = self.service.get_project(self.selected_project_id)
            with QSignalBlocker(self.outcome_check):
                self.outcome_check.setChecked(project.outcome_completed)
            self.error(exc)

    def add_work(self):
        p = self.selected_project()
        dialog = WorkLogDialog(p, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.operate(lambda: self.service.add_work(p.id, **dialog.payload()), "Time recorded. It counts.")

    def selected_log(self):
        item = self.logs_list.currentItem()
        if item:
            lid = item.data(Qt.ItemDataRole.UserRole)
            return next(log for log in self.selected_project().logs if log.id == lid)
        self.notify("Select a time record first.")
        return None

    def edit_work(self):
        log = self.selected_log()
        if log:
            p = self.selected_project()
            dialog = WorkLogDialog(p, log=log, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.operate(lambda: self.service.edit_work(p.id, log.id, **dialog.payload()), "Record updated; the plan has been recalculated.")

    def delete_work(self):
        log = self.selected_log()
        if log and QMessageBox.question(self, "Delete this record?", "Its minutes will be removed from the time bar. You can undo this record change.") == QMessageBox.StandardButton.Yes:
            self.operate(lambda: self.service.delete_work(self.selected_project_id, log.id))

    def focus_selected_task(self):
        if self.timer.state != "idle":
            self.show_page("focus")
            self.notify("A session is already open. Finish it before switching tasks.")
            return
        self.session_task_id = self.selected_task_id()
        self.show_page("focus")

    def build_focus(self):
        content = self.make_panel("Focus", "Choose a project and start a session.")
        active = [p for p in self.service.list_projects() if p.archived_at is None]
        if not active:
            content.addWidget(label("Create a project in your notebook to begin.", "muted", True))
            content.addWidget(button("+ Create a project", self.new_project, "primary"))
            content.addStretch()
            return
        self.focus_project_combo = QComboBox()
        fit_combo(self.focus_project_combo)
        for p in active:
            self.focus_project_combo.addItem(p.title, p.id)
        chosen = self.session_project_id if self.timer.state != "idle" else self.selected_project_id
        index = self.focus_project_combo.findData(chosen)
        self.focus_project_combo.setCurrentIndex(max(index, 0))
        self.focus_task_combo = QComboBox()
        fit_combo(self.focus_task_combo)
        self.populate_focus_tasks()
        self.focus_project_combo.currentIndexChanged.connect(self.populate_focus_tasks)
        content.addWidget(self.focus_project_combo)
        content.addWidget(self.focus_task_combo)
        content.addWidget(label("Choose a task or one of its subtasks. Both contribute to the task total, counted once per session.", "muted", True))
        self.clock_label = label("00:00")
        self.clock_label.setStyleSheet("font-family: 'Avenir Next'; font-size: 60px; font-weight: 300; color: #495B50;")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setMinimumHeight(102)
        content.addWidget(self.clock_label)
        self.focus_status = label("Ready to focus.", "muted")
        self.focus_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content.addWidget(self.focus_status)
        running = self.timer.state != "idle"
        self.focus_project_combo.setEnabled(not running)
        self.focus_task_combo.setEnabled(not running)
        self.start_button = button("Begin focus", self.start_focus, "primary")
        self.pause_button = button("Resume" if self.timer.state == "paused" else "Pause", self.pause_focus)
        self.finish_button = button("Finish and record", self.finish_focus, "primary")
        if running:
            content.addLayout(row(self.pause_button, self.finish_button))
        else:
            content.addWidget(self.start_button)
        content.addWidget(label("Pause when you step away. Check the date and minutes before saving.", "muted", True))
        if running:
            content.addWidget(button("Discard this session", self.discard_focus, "ghost"))
        content.addStretch()

    def populate_focus_tasks(self):
        pid = self.focus_project_combo.currentData()
        self.focus_task_combo.clear()
        self.focus_task_combo.addItem("Work on the whole project", None)
        if not pid:
            return
        def visit(nodes, path=()):
            for task in nodes:
                names = (*path, task.title)
                self.focus_task_combo.addItem(" / ".join(names), task.id)
                visit(task.children, names)
        visit(self.service.get_project(pid).tasks)
        index = self.focus_task_combo.findData(self.session_task_id)
        if index >= 0:
            self.focus_task_combo.setCurrentIndex(index)

    def start_focus(self):
        self.session_project_id = self.focus_project_combo.currentData()
        self.session_task_id = self.focus_task_combo.currentData()
        self.session_date = date.today()
        self.selected_project_id = self.session_project_id
        self.timer.start()
        self.activity.reset()
        self.activity.start()
        self._observe_focus_music(self.music_session.last_status)
        self.show_page("focus")

    def pause_focus(self):
        if self.timer.state == "paused":
            self.timer.resume()
            if self.activity.state == "paused":
                self.activity.resume()
            self._observe_focus_music(self.music_session.last_status)
        else:
            self._pause_focus_measurement()
        self.show_page("focus")

    def _observe_focus_music(self, status):
        self.activity.observe_music(status, player=self.music_session.app_id)

    def _clear_focus_music(self):
        self.activity.observe_music(None)

    def _pause_focus_measurement(self):
        if self.timer.state == "running":
            self.timer.pause()
        if self.activity.state == "running":
            self.activity.pause()

    def finish_focus(self):
        if self.timer.state == "idle":
            return True
        self._pause_focus_measurement()
        project = self.service.get_project(self.session_project_id)
        dialog = WorkLogDialog(project, initial_minutes=max(1, math.ceil(self.timer.elapsed_seconds() / 60)),
                               initial_date=self.session_date, initial_task_id=self.session_task_id, parent=self)
        dialog.subtitle_label.setText("Check the date and minutes. The chart keeps the timer's original intervals, with pauses excluded.")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.show_page("focus")
            return False
        try:
            self.service.add_work(project.id, **dialog.payload(), source="focus",
                                  focus_details=self.activity.snapshot())
        except (ValueError, OSError) as exc:
            self.error(exc)
            self.show_page("focus")
            return False
        self.timer.finish()
        self.activity.reset()
        self.session_project_id = self.session_task_id = self.session_date = None
        self.refresh_home()
        self.show_page("room")
        self.notify("Focus session saved.")
        return True

    def discard_focus(self):
        if QMessageBox.question(self, "Discard this session?", "This session will not be added to your time records.") == QMessageBox.StandardButton.Yes:
            self.timer.finish()
            self.activity.reset()
            self.session_project_id = self.session_task_id = self.session_date = None
            self.show_page("focus")

    def update_clock(self):
        elapsed = int(self.timer.elapsed_seconds())
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        text = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
        if self.clock_label:
            self.clock_label.setText(text)
            self.focus_status.setText({"idle": "Ready to focus.", "running": "Session running.", "paused": "Paused."}[self.timer.state])
        self.session_chip.setVisible(self.timer.state != "idle")
        self.session_chip.setText(f"{'Ⅱ' if self.timer.state == 'paused' else '●'}  {text}")
        if date.today() != self.last_date:
            self.last_date = date.today()
            self.date_label.setText(date.today().strftime("%A, %d %B"))
            self.refresh_home()
            if self.current_page == "plan" and self.isActiveWindow() and not self.immersive:
                self.show_page(self.current_page)

    def archive_project(self):
        p = self.selected_project()
        if self.timer.state != "idle" and self.session_project_id == p.id:
            self.notify("Finish this project's focus session before archiving it.")
            return
        dialog = NoteDialog(p.note, self, title="Archive project",
                            subtitle="Add a short reflection. You can archive an unfinished project and reopen it later.")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        def archive():
            self.service.update_project(p.id, note=dialog.payload())
            self.service.archive_project(p.id)
        self.current_page = "collection"
        self.operate(archive, "Project archived.")

    def build_collection(self):
        content = self.make_panel("Collection", "Archived projects, records and reflections.")
        content.addWidget(button("Design and arrange your books", self.edit_books, "primary"))
        archived = [p for p in self.service.list_projects() if p.archived_at is not None]
        archived.sort(key=lambda p: p.archived_at, reverse=True)
        if not archived:
            content.addWidget(label("No archived projects yet.", "section"))
            content.addWidget(label("Archive a project from Notebook when you want to put it aside. Its tasks and records will stay available here.", "muted", True))
            content.addWidget(button("Go to your notebook", lambda: self.show_page("plan"), "primary"))
        for p in archived:
            card = QFrame()
            card.setObjectName("subcard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(20, 18, 20, 18)
            layout.setSpacing(8)
            heading = QHBoxLayout()
            heading.addWidget(label(p.title, "section", True), 1)
            cover = QLabel()
            cover.setPixmap(self.book_cover_pixmap(p))
            cover.setFixedSize(94, 136)
            heading.addWidget(cover)
            layout.addLayout(heading)
            status = "Outcome achieved" if p.outcome_completed else "Outcome not marked complete"
            end = p.deadline.strftime('%d %b %Y') if p.deadline is not None else "no deadline"
            layout.addWidget(label(f"{p.start_date.strftime('%d %b')} — {end}   ·   {status}", "muted", True))
            actual = self.service.progress(p.id)["actual_minutes"]
            if p.deadline is None:
                layout.addWidget(label(f"{duration(actual)} recorded in total", "section"))
                layout.addWidget(label(f"Daily goal: {duration(p.daily_minutes)}", "muted"))
            else:
                layout.addWidget(EffortBar(actual, p.planned_minutes, p.color))
            if p.motivation:
                layout.addWidget(label("WHY I BEGAN", "eyebrow"))
                layout.addWidget(label(p.motivation, wrap=True))
            if p.note:
                layout.addWidget(label("REFLECTION", "eyebrow"))
                layout.addWidget(label(p.note, "muted", True))
            if p.image_path:
                path = Path(p.image_path)
                if not path.is_absolute():
                    path = self.data_path.parent / path
                photo = QPixmap(str(path))
                if not photo.isNull():
                    view = QLabel()
                    view.setPixmap(photo.scaled(340, 190, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    layout.addWidget(view)
                else:
                    layout.addWidget(label("The saved picture is unavailable. Your time records are intact.", "muted", True))
            if p.related_project_id:
                linked = self.service.get_project(p.related_project_id)
                layout.addWidget(label(f"Connected to: {linked.title}", "muted", True))
            layout.addLayout(row(button("Reopen project", lambda checked=False, pid=p.id: self.reopen_project(pid)),
                                 button("View records", lambda checked=False, pid=p.id: self.view_archived_records(pid), "ghost")))
            layout.addWidget(button("Design this book", lambda pid=p.id: self.edit_books(pid), "ghost"))
            appearance = self.book_service.appearance(p.id, p.color)
            layout.addWidget(button("Change cover" if appearance["cover_image"] else "Upload cover",
                                    lambda pid=p.id: self.upload_book_cover(pid)))
            content.addWidget(card)
        content.addStretch()

    def book_cover_pixmap(self, project):
        image = QPixmap(94, 136)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        appearance = self.book_service.appearance(project.id, project.color)
        draw_book(painter, QRectF(6, 8, 78, 120), appearance, project.title,
                  "cover", self.scene._book_image, 0)
        painter.end()
        return image

    def upload_book_cover(self, project_id):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose this book's cover", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not filename:
            return
        target = None
        try:
            source = Path(filename)
            if source.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("Choose an image no larger than 10 MB.")
            reader = QImageReader(str(source))
            size = reader.size()
            if not reader.canRead() or not size.isValid() or size.width()*size.height() > 25_000_000 or reader.read().isNull():
                raise ValueError("Choose a readable image smaller than 25 million pixels.")
            project = self.service.get_project(project_id)
            relative = Path("book-images") / (uuid4().hex + source.suffix.lower())
            target = self.data_path.parent / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            appearance = self.book_service.appearance(project_id, project.color)
            appearance["cover_image"] = relative.as_posix()
            placement = self.book_service.placement(project_id, self.BOOK_LAYOUT_ID)
            self.book_service.save_book(project_id, appearance, self.BOOK_LAYOUT_ID,
                                        placement["slot"], placement["facing"], self.service.list_projects())
        except (ValueError, OSError) as exc:
            if target:
                target.unlink(missing_ok=True)
            self.error(exc)
            return
        self.refresh_home()
        self.show_page("collection")
        self.notify("Cover copied and saved with this book.")

    def reopen_project(self, pid):
        def reopen():
            self.service.reopen_project(pid)
            self.selected_project_id = pid
        self.current_page = "plan"
        self.operate(reopen, "Back on your desk. All previous effort is preserved.")

    def view_archived_records(self, pid):
        project = self.service.get_project(pid)
        dialog = QDialog(self)
        dialog.setWindowTitle(project.title + " — time records")
        dialog.resize(620, 480)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label("Project time records", "section"))
        tabs = QTabWidget()
        statistics = RecordStatsPanel(self, project, dialog)
        if project.logs:
            on = max(log.worked_on for log in project.logs)
            statistics.date_input.setDate(QDate(on.year, on.month, on.day))
        tabs.addTab(statistics, "Overview")
        listing = QListWidget()
        for log in sorted(project.logs, key=lambda log: log.worked_on, reverse=True):
            item = QListWidgetItem(f"{log.worked_on.isoformat()}  ·  {duration(log.minutes)}\n{log.note}")
            listing.addItem(item)
        tabs.addTab(listing, "Entries")
        if not any(log.focus_details for log in project.logs):
            tabs.setCurrentIndex(1)
        layout.addWidget(tabs, 1)
        layout.addWidget(button("Close", dialog.accept, "primary"))
        dialog.exec()

    def shuffle_room_note(self):
        self.current_note = select_next_note(self.notes, self.current_note)
        self.room_note.set_note(self.current_note)
        self.room_note.set_shuffle_enabled(len(set(self.notes)) > 1)
        self.note_label.setText(self.current_note)

    def edit_room_note(self):
        if self.settings_error:
            self.error("The existing room settings could not be read. Repair room-settings.json before saving; the original is preserved.")
            return
        dialog = NotesDialog(self.notes, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new = {**self.settings, "notes": dialog.payload()}
            try:
                self.settings_repository.save(new)
            except OSError as exc:
                self.error(exc)
                return
            self.settings = new
            self.notes = normalize_notes(new)
            self.shuffle_room_note()
            self.notify("Your notes are saved.")

    def _motion_caption(self):
        self.motion_button.setText("Animation: on" if self.scene.motion else "Animation: off")

    def toggle_motion(self):
        if self.settings_error:
            self.scene.set_motion(not self.scene.motion)
            self._motion_caption()
            return
        new = {**self.settings, "motion": not self.scene.motion}
        try:
            self.settings_repository.save(new)
        except OSError as exc:
            self.error(exc)
            return
        self.settings = new
        self.scene.set_motion(new["motion"])
        self._motion_caption()

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
        self.fullscreen_button.setText("Leave full screen" if self.isFullScreen() else "Full screen")

    def toggle_night_mode(self):
        enabled = not self.scene.night_mode
        if not self.settings_error:
            updated = {**self.settings, "night_mode": enabled}
            try:
                self.settings_repository.save(updated)
            except OSError as exc:
                self.night_button.setChecked(self.scene.night_mode)
                self.error(exc)
                return
            self.settings = updated
        self.scene.set_night_mode(enabled)
        self._apply_color_mode()

    def _apply_color_mode(self, repolish=True):
        night = self.scene.night_mode
        if repolish:
            self.setStyleSheet(NIGHT_STYLE if night else STYLE)
        ink = "#DDE2D7" if night else "#35413B"
        muted = "#A2AD9E" if night else "#788074"
        self.brand_label.setStyleSheet(f"font-family: Georgia; font-size: 29px; color: {ink};")
        self.hero_title.setStyleSheet(f"font-family: Georgia; font-size: 44px; color: {ink};")
        self.footer_surface.setStyleSheet("background: #1F2831;" if night else "background: #EEEAE1;")
        self.footer_rule.setStyleSheet("background: #465149;" if night else "background: #CBCFC1;")
        self.local_label.setStyleSheet(f"font-size: 10px; color: {muted};")
        self.toast.setStyleSheet("background: #344439; color: #E2E7D9; border: 1px solid #5D705D; border-radius: 5px; padding: 10px 14px;" if night else "background: #E5E9DE; color: #35413B; border: 1px solid #BEC8B9; border-radius: 5px; padding: 10px 14px;")
        self.night_button.setText("Day mode" if night else "Night mode")
        self.night_button.setChecked(night)
        self.room_note.set_night_mode(night)
        if self.clock_label:
            self.clock_label.setStyleSheet(f"font-family: 'Avenir Next'; font-size: 60px; font-weight: 300; color: {'#C7D4B6' if night else '#495B50'};")

    def escape(self):
        if self.immersive:
            self.leave_immersion()
        elif self.current_page != "room":
            self.show_page("room")
        elif self.isFullScreen():
            self.toggle_fullscreen()

    def show_help(self):
        QMessageBox.information(self, "Welcome to Anchor",
            "Five views of one study. Room shows the whole space; Notebook moves to the bookshelf; Focus to the desk; Collection to the reading corner; Music to the listening corner.\n\n"
            "Your projects have books on the shelf. Open one to see its tasks and time records. Use Design and arrange books (Ctrl+B) to edit covers, spines and positions.\n\n"
            "Hide interface (Ctrl+I) removes controls. The window opens a closer view of the same landscape. Esc or double-click returns; your focus session and music continue.\n\n"
            "Music connects to Spotify or Apple Music on macOS. Select music in the player, then Connect; macOS may ask for Automation permission.\n\n"
            "Ctrl+1–5 changes views; Ctrl+N adds a project; F11 toggles full screen. Your notes and animation settings are in the top-right options menu. Notes can be added individually and one appears each time you return to Room.\n\n"
            "Notebook is a flat workspace with paged tasks, dates and records. New goals may have no deadline. Gentle catch-up is optional in Edit goal; extra time is capped at 25% and 15 minutes. Archived books accept cover uploads in Collection.\n\n"
            "Records → Overview shows saved focus intervals by local hour and music observed during them. Choose a date and This goal or All goals. Pause time is excluded; connect a music player to capture tracks. Earlier records without timing are labelled.\n\n"
            "Confirm focus time before closing. Active timers cannot be recovered after a crash.")

    def closeEvent(self, event):
        if self.timer.state == "idle":
            self.music_session.shutdown()
            event.accept()
            return
        self._pause_focus_measurement()
        choice = QMessageBox.question(self, "Keep this focus session?", "Save the session before closing? Choose No to discard it, or Cancel to stay in the room.",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                                      QMessageBox.StandardButton.Cancel)
        if choice == QMessageBox.StandardButton.Yes:
            if self.finish_focus():
                self.music_session.shutdown()
                event.accept()
            else:
                event.ignore()
        elif choice == QMessageBox.StandardButton.No:
            self.timer.finish()
            self.activity.reset()
            self.music_session.shutdown()
            event.accept()
        else:
            self.show_page("focus")
            event.ignore()
