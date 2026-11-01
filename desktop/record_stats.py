"""Daily focus totals, hourly bars and observed tracks."""

from html import escape

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from planner.statistics import summarize_day
from .focus_chart import FocusHourChart
from .input_controls import DateInput


def _label(text="", role=None):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        item.setObjectName(role)
    return item


def _button(text, action, accessible):
    item = QPushButton(text)
    item.setObjectName("ghost")
    item.setStyleSheet("padding: 1px 5px; min-height: 22px; border: none;")
    item.setAccessibleName(accessible)
    item.setToolTip(accessible)
    item.clicked.connect(lambda checked=False: action())
    return item


def _duration(seconds):
    if 0 < seconds < 60:
        return f"{round(seconds)}s"
    minutes = round(seconds / 60)
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}m" if hours else f"{minutes}m"


class RecordStatsPanel(QWidget):
    def __init__(self, window, project, parent=None):
        super().__init__(parent)
        self.window, self.project_id = window, project.id
        self.track_page = 0
        self.track_count = 1
        self.summary = {}
        self.setMinimumWidth(0)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 8, 0, 0)
        self.main_layout.setSpacing(10)
        header = QHBoxLayout()
        header.setSpacing(16)
        figure = QVBoxLayout()
        figure.setSpacing(0)
        self.total_label = _label()
        self.total_label.setAccessibleName("Daily focus duration")
        self.total_label.setStyleSheet("font-family: Georgia; font-size: 34px; font-weight: 400;")
        self.total_caption = _label("Focused", "muted")
        self.total_caption.setStyleSheet("font-size: 11px;")
        figure.addWidget(self.total_label)
        figure.addWidget(self.total_caption)
        header.addLayout(figure, 1)
        filters = QVBoxLayout()
        filters.setSpacing(2)
        controls = QHBoxLayout()
        controls.setSpacing(0)
        controls.addWidget(_button("‹", lambda: self.move_date(-1), "Previous statistics date"))
        self.date_input = DateInput(QDate.currentDate())
        self.date_input.setDate(QDate(window.service.today().year, window.service.today().month, window.service.today().day))
        self.date_input.setDisplayFormat("dd MMM yyyy")
        self.date_input.setFixedWidth(146)
        self.date_input.button.setStyleSheet("background: transparent; border: none; text-align: center; padding: 2px 3px; min-height: 22px;")
        controls.addWidget(self.date_input)
        controls.addWidget(_button("›", lambda: self.move_date(1), "Next statistics date"))
        filters.addLayout(controls)
        self.scope_combo = QComboBox()
        self.scope_combo.addItem("This goal", "project")
        self.scope_combo.addItem("All goals", "all")
        self.scope_combo.setAccessibleName("Statistics scope")
        self.scope_combo.setFixedWidth(120)
        self.scope_combo.setStyleSheet("background: transparent; border: none; padding: 1px 5px; min-height: 20px; font-size: 11px;")
        filters.addWidget(self.scope_combo, alignment=Qt.AlignmentFlag.AlignRight)
        header.addLayout(filters)
        self.main_layout.addLayout(header)
        self.chart = FocusHourChart()
        self.main_layout.addWidget(self.chart, 1)
        self.music_area = QWidget()
        self.music_area.setObjectName("statsMusic")
        music_layout = QVBoxLayout(self.music_area)
        music_layout.setContentsMargins(0, 8, 0, 0)
        music_layout.setSpacing(5)
        music = QHBoxLayout()
        music.setSpacing(2)
        self.music_title = _label("Music", "muted")
        self.music_title.setStyleSheet("font-size: 11px; font-weight: 600;")
        self.music_title.setToolTip("Tracks observed during saved focus intervals. Connect Spotify or Apple Music to capture music; polling every two seconds gives approximate boundaries.")
        music.addWidget(self.music_title, 1)
        self.previous_track = _button("‹", lambda: self.move_track(-1), "Previous observed tracks")
        self.next_track = _button("›", lambda: self.move_track(1), "Next observed tracks")
        self.track_counter = _label("", "muted")
        for child in (self.previous_track, self.track_counter, self.next_track):
            music.addWidget(child)
        music_layout.addLayout(music)
        self.track_labels = [_label(), _label()]
        self.track_durations = [_label("", "muted"), _label("", "muted")]
        self.track_rows = []
        for child, amount in zip(self.track_labels, self.track_durations):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(14)
            child.setMinimumWidth(0)
            child.setStyleSheet("font-size: 12px;")
            amount.setStyleSheet("font-size: 12px;")
            amount.setFixedWidth(66)
            amount.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row_layout.addWidget(child, 1)
            row_layout.addWidget(amount)
            music_layout.addWidget(row)
            self.track_rows.append(row)
        self.main_layout.addWidget(self.music_area)
        self.status_label = _label("", "muted")
        self.status_label.setStyleSheet("font-size: 10px;")
        self.main_layout.addWidget(self.status_label)
        self.date_input.dateChanged.connect(lambda on: self.refresh())
        self.scope_combo.currentIndexChanged.connect(lambda index: self.refresh())
        self.refresh()

    def sizeHint(self):
        return QSize(640, 410)

    def minimumSizeHint(self):
        return QSize(320, 260)

    def move_date(self, direction):
        on = self.date_input.date().addDays(direction)
        if on.isValid():
            self.date_input.setDate(on)

    def refresh(self):
        project = self.window.service.get_project(self.project_id)
        projects = self.window.service.list_projects() if self.scope_combo.currentData() == "all" else [project]
        # Confirmed record totals can differ from the timer's observed intervals.
        self.summary = summarize_day(projects, self.date_input.date().toPython())
        measured = _duration(self.summary["measured_focus_seconds"])
        recorded = self.summary["recorded_focus_minutes"]
        if not self.summary["has_timing"] and recorded:
            self.total_label.setText(_duration(recorded * 60))
            self.total_caption.setText("Recorded focus · timing unavailable")
        else:
            self.total_label.setText(measured)
            self.total_caption.setText("Focused" if abs(self.summary["measured_focus_seconds"] - recorded*60) < 1
                                       else f"Focused · {recorded}m recorded focus")
        self.total_label.setToolTip(f"{measured} captured · {recorded}m recorded focus. Captured duration uses observed timer intervals; the confirmed work date and minutes can be edited independently.")
        self.total_label.setAccessibleDescription(self.total_label.toolTip())
        self.chart.set_minutes(self.summary["hourly_minutes"], self.summary["hourly_periods"])
        self.track_page = 0
        self.show_tracks()
        if self.summary["untimed_focus_minutes"]:
            text = f"{self.summary['untimed_focus_minutes']}m of focus has no captured time of day."
        else:
            text = ""
        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
        self.status_label.setToolTip("Older/manual records are never assigned guessed hours. Bars use observed timestamps; work-date edits only change the recorded total. Music is observed from the connected player, not a complete listening history. Repeated DST hours share a column.")

    def show_tracks(self):
        tracks = self.summary.get("tracks", [])
        pages = max(1, (len(tracks)+self.track_count-1)//self.track_count)
        self.track_page = min(max(0, self.track_page), pages-1)
        shown = tracks[self.track_page*self.track_count:(self.track_page+1)*self.track_count]
        for index, label in enumerate(self.track_labels):
            self.track_rows[index].setVisible(index < max(1, len(shown)))
            amount = self.track_durations[index]
            if index < len(shown):
                track = shown[index]
                name = track["title"] + (" — " + track["artist"] if track["artist"] else "")
                full = name + " · " + _duration(track["seconds"])
                label.setText(label.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, max(40, self.width()-84)))
                amount.setText(_duration(track["seconds"]))
                tooltip = full + ("\n" + track["player"] if track["player"] else "")
                label.setToolTip("<qt>" + escape(tooltip).replace("\n", "<br>") + "</qt>")
            elif index == 0:
                label.setText("No music captured")
                amount.setText("")
                label.setToolTip("Connect Spotify or Apple Music before focusing to capture track changes. Unconnected periods remain unknown.")
            else:
                label.setText("")
                amount.setText("")
        self.track_counter.setText(f"{self.track_page+1} / {pages}")
        for control in (self.previous_track, self.track_counter, self.next_track):
            control.setVisible(pages > 1)
        self.previous_track.setEnabled(self.track_page > 0)
        self.next_track.setEnabled(self.track_page < pages-1)

    def move_track(self, direction):
        self.track_page += direction
        self.show_tracks()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        count = 2 if self.height() >= 350 else 1
        first = self.track_page * self.track_count
        self.track_count = count
        self.track_page = first // count
        spacious = self.height() >= 380
        self.main_layout.setSpacing(18 if spacious else 10)
        self.main_layout.setContentsMargins(0, 14 if spacious else 8, 0, 0)
        self.show_tracks()
