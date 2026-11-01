"""Project, record and note forms. Saving is handled by the caller."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from PySide6.QtCore import QDate, QTime, Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QSizePolicy, QTabWidget, QTextEdit, QTimeEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from planner.models import TaskNode
from planner.activity import validate_work_intervals, work_interval_minutes
from planner.statistics import local_timezone

from .input_controls import DateInput, DurationInput


PALETTE = (
    ("Lavender", "#A79ACB"),
    ("Sage", "#8FB3A2"),
    ("Amber", "#D7B481"),
    ("Rose", "#C394A0"),
    ("Blue", "#8FAEC9"),
    ("Terracotta", "#C78D78"),
)


def _qdate(value: date) -> QDate:
    return QDate(value.year, value.month, value.day)


def _date_input(value: date, minimum: date) -> DateInput:
    field = DateInput(_qdate(value))
    field.setMinimumDate(_qdate(minimum))
    field.setDate(_qdate(value))
    return field


def _minutes(value: int, presets=(15, 25, 45, 60)) -> DurationInput:
    field = DurationInput(value, presets)
    field.setRange(1, 10_000_000)
    field.setValue(value)
    return field


class _InputDialog(QDialog):
    """Common form layout and validation messages."""

    def __init__(self, title, subtitle, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.resize(520, 420)
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(26, 24, 26, 24)
        self.layout_box.setSpacing(12)
        heading = QLabel(title)
        heading.setObjectName("dialogTitle")
        font = heading.font()
        font.setPointSize(20)
        font.setBold(False)
        heading.setFont(font)
        self.heading_label = heading
        self.layout_box.addWidget(heading)
        hint = QLabel(subtitle)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        self.subtitle_label = hint
        self.layout_box.addWidget(hint)
        self.form = QFormLayout()
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.form.setHorizontalSpacing(18)
        self.form.setVerticalSpacing(10)
        self.layout_box.addLayout(self.form)

    def _add_buttons(self, save_text="Save"):
        self.error_label = QLabel()
        self.error_label.setObjectName("error")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.layout_box.addWidget(self.error_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText(save_text)
        self.save_button.setObjectName("primary")
        self.save_button.setDefault(True)
        self.cancel_button = self.buttons.button(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout_box.addWidget(self.buttons)

    def _show_error(self, message):
        self.error_label.setText(message)
        self.error_label.setVisible(True)


class TaskOutlineEditor(QWidget):
    """Prepare a two-level task outline before the project is saved."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(10)
        hint = QLabel("Add a task, then select it to add smaller steps. You can focus on either level.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName("Initial tasks and subtasks")
        self.tree.setMinimumHeight(180)
        self.tree.setToolTip("Double-click a task name to rename it.")
        layout.addWidget(self.tree, 1)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Name a task or a smaller step")
        self.name_edit.setAccessibleName("New task name")
        self.name_edit.setMaxLength(200)
        layout.addWidget(self.name_edit)
        actions = QHBoxLayout()
        self.add_task_button = QPushButton("+ Task")
        self.add_subtask_button = QPushButton("+ Subtask")
        self.remove_button = QPushButton("Remove")
        for button in (self.add_task_button, self.add_subtask_button, self.remove_button):
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.add_task_button.clicked.connect(lambda: self.add_task())
        self.add_subtask_button.clicked.connect(lambda: self.add_task(as_subtask=True))
        self.remove_button.clicked.connect(self.remove_selected)
        self.name_edit.returnPressed.connect(self.add_task)
        self.name_edit.textChanged.connect(self.update_actions)
        self.tree.itemSelectionChanged.connect(self.update_actions)
        self.update_actions()

    def update_actions(self, *args):
        selected = self.tree.currentItem()
        has_name = bool(self.name_edit.text().strip())
        self.add_task_button.setEnabled(has_name)
        self.add_subtask_button.setEnabled(has_name and selected is not None and selected.parent() is None)
        self.add_subtask_button.setToolTip("Select a top-level task to add a subtask.")
        self.remove_button.setEnabled(selected is not None)

    def add_task(self, as_subtask=False):
        title = self.name_edit.text().strip()
        parent = self.tree.currentItem() if as_subtask else None
        if not title or (as_subtask and (parent is None or parent.parent() is not None)):
            return
        item = QTreeWidgetItem([title])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
            parent.setExpanded(True)
        self.tree.setCurrentItem(item)
        self.name_edit.clear()
        self.name_edit.setFocus()

    def remove_selected(self):
        item = self.tree.currentItem()
        if item is None:
            return
        parent = item.parent()
        if parent is None:
            self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        else:
            parent.takeChild(parent.indexOfChild(item))
        self.update_actions()

    def tasks(self):
        def node(item):
            title = item.text(0).strip()
            if not title:
                raise ValueError("Give every task a name, or remove the empty task.")
            return TaskNode(title, children=[node(item.child(i)) for i in range(item.childCount())])
        return [node(self.tree.topLevelItem(i)) for i in range(self.tree.topLevelItemCount())]


class ProjectDialog(_InputDialog):
    """Edit project settings while keeping the original total estimate fixed."""

    def __init__(self, project=None, projects=(), parent=None):
        super().__init__(
            "Edit your goal" if project else "A new goal",
            "Choose a daily pace. A deadline and gentle catch-up are optional.",
            parent,
        )
        self.project = project
        self._effort_driver = "daily"
        self._syncing_effort = False
        self._effort_link_error = None
        self.setMinimumWidth(560)
        self.resize(620, 590)
        self.task_editor = None
        if project is None:
            self.layout_box.removeItem(self.form)
            self.form.setParent(None)
            settings = QWidget()
            settings.setLayout(self.form)
            self.tabs = QTabWidget()
            self.tabs.addTab(settings, "Project")
            self.task_editor = TaskOutlineEditor()
            self.tabs.addTab(self.task_editor, "Tasks (optional)")
            self.layout_box.addWidget(self.tabs, 1)
        self.title_edit = QLineEdit(project.title if project else "")
        self.title_edit.setPlaceholderText("What would you like to work towards?")
        self.title_edit.setMaxLength(200)
        start_date = project.start_date if project else date.today()
        self.deadline_edit = _date_input(
            # The default ten-day plan fits 300 minutes at 30 minutes a day.
            project.deadline if project and project.deadline else date.today() + timedelta(days=9), start_date
        )
        self.no_deadline_check = QCheckBox("No deadline")
        self.no_deadline_checkbox = self.no_deadline_check
        self.no_deadline_check.setChecked(project is not None and project.deadline is None)
        timing = QWidget()
        timing_layout = QHBoxLayout(timing)
        timing_layout.setContentsMargins(0, 0, 0, 0)
        timing_layout.setSpacing(12)
        timing_layout.addWidget(self.no_deadline_check)
        timing_layout.addWidget(self.deadline_edit, 1)
        self.planned_minutes = _minutes(project.planned_minutes if project else 300, (60, 180, 300))
        self.planned_minutes.setEnabled(project is None)
        self.daily_minutes = _minutes(project.daily_minutes if project else 30)
        self.daily_limit_minutes = _minutes(project.daily_limit_minutes if project else 60, (30, 60, 90, 120))
        self.catch_up_check = QCheckBox("Allow gentle catch-up")
        self.catch_up_check.setChecked(getattr(project, "catch_up_enabled", True) if project else False)
        self.catch_up_check.setToolTip("Adds at most 25% of your usual pace, capped at 15 min/day and your daily maximum. Ongoing goals only look at yesterday; older missed days do not stack.")
        self.color_combo = QComboBox()
        for name, color in PALETTE:
            self.color_combo.addItem(name, color)
            self.color_combo.setItemData(
                self.color_combo.count() - 1, QColor(color), Qt.ItemDataRole.DecorationRole
            )
        if project:
            index = self.color_combo.findData(project.color)
            if index < 0:
                self.color_combo.addItem("Current colour", project.color)
                index = self.color_combo.count() - 1
                self.color_combo.setItemData(index, QColor(project.color), Qt.ItemDataRole.DecorationRole)
            self.color_combo.setCurrentIndex(index)
        self.related_combo = QComboBox()
        self.related_combo.addItem("No related project", None)
        for other in projects:
            if project is None or other.id != project.id:
                self.related_combo.addItem(other.title, other.id)
        if project and project.related_project_id:
            index = self.related_combo.findData(project.related_project_id)
            if index >= 0:
                self.related_combo.setCurrentIndex(index)
        for combo in (self.color_combo, self.related_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(8)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.color_combo.setToolTip("Book colour")
        self.related_combo.setToolTip("Connect this goal to another project (optional)")
        details = QWidget()
        details_layout = QHBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(8)
        details_layout.addWidget(self.color_combo, 1)
        details_layout.addWidget(self.related_combo, 2)
        self.motivation_edit = QTextEdit()
        self.motivation_edit.setAcceptRichText(False)
        self.motivation_edit.setPlainText(project.motivation if project else "")
        self.motivation_edit.setPlaceholderText("Why does this matter to you?")
        self.motivation_edit.setFixedHeight(58)
        self.form.addRow("Project", self.title_edit)
        self.form.addRow("Timing", timing)
        self.form.addRow("Original effort", self.planned_minutes)
        self.form.addRow("Daily goal", self.daily_minutes)
        self.effort_link_label = QLabel()
        self.effort_link_label.setObjectName("muted")
        self.effort_link_label.setWordWrap(True)
        self.form.addRow("", self.effort_link_label)
        self.form.addRow("Daily maximum", self.daily_limit_minutes)
        self.form.addRow("Book / connection", details)
        self.form.addRow("Your reason", self.motivation_edit)
        catch_up = QWidget()
        catch_layout = QVBoxLayout(catch_up)
        catch_layout.setContentsMargins(0, 0, 0, 0)
        catch_layout.setSpacing(4)
        catch_layout.addWidget(self.catch_up_check)
        catch_hint = QLabel("Optional · at most 25% extra, capped at 15 min/day.")
        catch_hint.setObjectName("muted")
        catch_hint.setWordWrap(True)
        catch_layout.addWidget(catch_hint)
        self.form.addRow("Catch-up", catch_up)
        if project:
            fixed_hint = QLabel("Your original effort target stays fixed so your time bar keeps its meaning.")
            fixed_hint.setObjectName("muted")
            fixed_hint.setWordWrap(True)
            self.fixed_hint = fixed_hint
            self.layout_box.addWidget(fixed_hint)
        self._add_buttons("Save changes" if project else "Create project")
        if self.task_editor is not None:
            self.tabs.currentChanged.connect(self._set_default_action)
            self._set_default_action(0)
        self.daily_minutes.valueChanged.connect(self._keep_cap_above_daily_goal)
        for name, field in (("daily", self.daily_minutes), ("total", self.planned_minutes)):
            field.valueChanged.connect(lambda amount, source=name: self._effort_changed(source))
            field.editor.textEdited.connect(lambda text, source=name: self._effort_changed(source))
            for preset in field.preset_buttons.values():
                preset.clicked.connect(lambda checked=False, source=name: self._effort_changed(source))
        self.deadline_edit.dateChanged.connect(self._sync_effort)
        self.no_deadline_check.toggled.connect(self._update_deadline_mode)
        self._update_deadline_mode()
        self.title_edit.setFocus()

    def _set_default_action(self, index):
        # Enter adds a draft task without submitting the whole project.
        self.save_button.setAutoDefault(index == 0)
        self.save_button.setDefault(index == 0)
        self.cancel_button.setAutoDefault(False)

    def _keep_cap_above_daily_goal(self, amount):
        try:
            if self.daily_limit_minutes.value() < amount:
                self.daily_limit_minutes.setValue(amount)
        except ValueError:
            # Let Save report invalid input instead of replacing an unfinished edit.
            return

    def _effort_changed(self, source):
        if self._syncing_effort or self.project is not None:
            return
        field = self.daily_minutes if source == "daily" else self.planned_minutes
        try:
            field.value()
        except ValueError:
            self.effort_link_label.setText("Finish entering a valid duration to update the linked estimate.")
            return
        self._effort_driver = source
        self._sync_effort(from_edit=True)

    def _sync_effort(self, *args, from_edit=False):
        if self._syncing_effort:
            return
        self._effort_link_error = None
        if self.project is not None:
            self.form.setRowVisible(self.effort_link_label, False)
            return
        self.effort_link_label.setVisible(True)
        if self.no_deadline_check.isChecked():
            self.effort_link_label.setText("An ongoing goal follows your daily pace, without a total-effort target.")
            return
        days = (self.deadline_edit.date().toPython() - date.today()).days + 1
        if days < 1:
            self.effort_link_label.setText("Choose today or a later deadline to calculate your pace.")
            return
        source = self.daily_minutes if self._effort_driver == "daily" else self.planned_minutes
        target = self.planned_minutes if self._effort_driver == "daily" else self.daily_minutes
        try:
            amount = source.value()
            if not from_edit:
                target.value()  # Do not replace an unfinished edit when dates change.
        except ValueError:
            self.effort_link_label.setText("Finish entering a valid duration to update the linked estimate.")
            return
        derived = amount * days if self._effort_driver == "daily" else (amount + days - 1) // days
        if derived > target.maximum():
            self._effort_link_error = "This date range exceeds the supported total effort. Reduce the daily goal or choose an earlier deadline."
            self.effort_link_label.setText(self._effort_link_error)
            return
        self._syncing_effort = True
        try:
            target.setValue(derived)
        finally:
            self._syncing_effort = False
        day_word = "day" if days == 1 else "days"
        if self._effort_driver == "daily":
            explanation = f"{days} {day_word}, including today and the deadline. Total = daily goal × days."
        else:
            explanation = f"{days} {day_word}, including today and the deadline. Daily goal = total ÷ days, rounded up to a whole minute."
        self.effort_link_label.setText(explanation)

    def _update_deadline_mode(self, *args):
        ongoing = self.no_deadline_check.isChecked()
        self.deadline_edit.setVisible(not ongoing)
        self.form.setRowVisible(self.planned_minutes, not ongoing)
        if hasattr(self, "fixed_hint"):
            self.fixed_hint.setVisible(not ongoing)
        self.no_deadline_check.setToolTip("An ongoing goal uses your daily target, without a finish date or a total-effort limit.")
        self._sync_effort()

    def payload(self) -> dict:
        values = {
            "title": self.title_edit.text().strip(),
            "deadline": None if self.no_deadline_check.isChecked() else self.deadline_edit.date().toPython(),
            "daily_minutes": self.daily_minutes.value(),
            "daily_limit_minutes": self.daily_limit_minutes.value(),
            "color": self.color_combo.currentData(),
            "motivation": self.motivation_edit.toPlainText().strip(),
            "related_project_id": self.related_combo.currentData(),
            "catch_up_enabled": self.catch_up_check.isChecked(),
        }
        if self.project is None:
            values["planned_minutes"] = 300 if self.no_deadline_check.isChecked() else self.planned_minutes.value()
            values["tasks"] = self.task_editor.tasks()
        return values

    def accept(self):
        if self.task_editor is not None:
            if self.task_editor.name_edit.text().strip():
                self.tabs.setCurrentIndex(1)
                self._show_error("Add the task name to your outline, or clear it before creating the project.")
                self.task_editor.name_edit.setFocus()
                return
            try:
                self.task_editor.tasks()
            except ValueError as exc:
                self.tabs.setCurrentIndex(1)
                self._show_error(str(exc))
                self.task_editor.tree.setFocus()
                return
        try:
            fields = (self.daily_minutes, self.daily_limit_minutes)
            if not self.no_deadline_check.isChecked():
                fields = (self.planned_minutes, *fields)
            for field in fields:
                field.interpretText()
            self._sync_effort()
            if self._effort_link_error:
                self._show_error(self._effort_link_error)
                if self.task_editor is not None:
                    self.tabs.setCurrentIndex(0)
                self.daily_minutes.setFocus()
                return
            values = self.payload()
        except ValueError as exc:
            self._show_error(str(exc))
            if self.task_editor is not None:
                self.tabs.setCurrentIndex(0)
            field.setFocus()
            return
        if not values["title"]:
            self._show_error("Give your project a name before saving.")
            if self.task_editor is not None:
                self.tabs.setCurrentIndex(0)
            self.title_edit.setFocus()
            return
        if values["daily_limit_minutes"] < values["daily_minutes"]:
            self._show_error("The daily suggestion cap must be at least your daily rhythm.")
            if self.task_editor is not None:
                self.tabs.setCurrentIndex(0)
            self.daily_limit_minutes.setFocus()
            return
        if values["deadline"] is not None and values["deadline"] < (self.project.start_date if self.project else date.today()):
            self._show_error("The deadline cannot be earlier than the project start date.")
            return
        super().accept()


class _PeriodEndpoint(QWidget):
    changed = Signal()

    def __init__(self, stamp, minimum, parent=None):
        super().__init__(parent)
        self.zone = local_timezone()
        self.original = stamp.astimezone(self.zone)
        # Display imported times unchanged; Save reports invalid dates.
        self.date_input = _date_input(self.original.date(), min(minimum, self.original.date()))
        self.date_input.setMaximumDate(_qdate(max(date.today(), self.original.date())))
        self.date_input.button.setAccessibleName('Choose period date')
        self.time_input = QTimeEdit(QTime(self.original.hour, self.original.minute, self.original.second))
        self.time_input.setDisplayFormat('HH:mm:ss')
        self.time_input.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.time_input.setFixedWidth(104)
        self.time_input.setAccessibleName('Time in hours, minutes and seconds')
        self.time_input.setToolTip('Local time · hours:minutes:seconds')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.date_input, 1)
        layout.addWidget(self.time_input)
        self.date_input.dateChanged.connect(lambda value: self.changed.emit())
        self.time_input.timeChanged.connect(lambda value: self.changed.emit())

    def value(self):
        day = self.date_input.date().toPython()
        clock = self.time_input.time().toPython()
        if day == self.original.date() and clock == self.original.time().replace(tzinfo=None, microsecond=0):
            return self.original  # Preserve captured fractions and repeated-hour offsets.
        stamp = datetime.combine(day, clock, tzinfo=self.zone)
        if stamp.astimezone(timezone.utc).astimezone(self.zone).replace(tzinfo=None) != stamp.replace(tzinfo=None):
            raise ValueError('This local time does not exist because the clocks change. Choose another time.')
        return stamp


class WorkPeriodEditor(QWidget):
    """Edit real start/end points; duration is calculated from these periods."""

    changed = Signal()

    def __init__(self, intervals, minimum, parent=None):
        super().__init__(parent)
        self.minimum = minimum
        self.rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        headings = QHBoxLayout()
        headings.addWidget(QLabel('Start'), 1)
        headings.addWidget(QLabel('End'), 1)
        headings.addSpacing(36)
        layout.addLayout(headings)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.period_layout = QVBoxLayout(self.content)
        self.period_layout.setContentsMargins(0, 0, 0, 0)
        self.period_layout.setSpacing(6)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll)
        self.add_button = QPushButton('+ Add period')
        self.add_button.setObjectName('ghost')
        self.add_button.setAutoDefault(False)
        self.add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_button.clicked.connect(lambda: self.add_period())
        layout.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignLeft)
        for span in intervals:
            self.add_period(datetime.fromisoformat(span['started_at'].replace('Z', '+00:00')),
                            datetime.fromisoformat(span['ended_at'].replace('Z', '+00:00')))

    def add_period(self, start=None, end=None):
        added_by_user = start is None
        if start is None:
            try:
                start = self.rows[-1][2].value() if self.rows else datetime.now().astimezone()
            except ValueError:
                self.changed.emit()
                return
            end = start
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        beginning = _PeriodEndpoint(start, self.minimum)
        ending = _PeriodEndpoint(end, self.minimum)
        remove = QPushButton('×')
        remove.setObjectName('ghost')
        remove.setFixedWidth(30)
        remove.setStyleSheet('padding: 6px 0;')
        remove.setAutoDefault(False)
        remove.setAccessibleName('Remove this period')
        remove.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(beginning, 1)
        row.addWidget(ending, 1)
        row.addWidget(remove)
        entry = (widget, beginning, ending, remove)
        self.rows.append(entry)
        self.period_layout.addWidget(widget)
        beginning.changed.connect(self.changed)
        ending.changed.connect(self.changed)
        remove.clicked.connect(lambda: self.remove_period(entry))
        self._fit_rows()
        self.changed.emit()
        if added_by_user:
            # Wait for the new row's geometry before scrolling to its inputs.
            QTimer.singleShot(0, widget, lambda: self._reveal_period(widget, beginning))

    def _reveal_period(self, widget, beginning):
        self.period_layout.activate()
        self.content.adjustSize()
        self.scroll.ensureWidgetVisible(widget)
        beginning.time_input.setFocus()
        beginning.time_input.selectAll()

    def remove_period(self, entry):
        self.rows.remove(entry)
        self.period_layout.removeWidget(entry[0])
        entry[0].deleteLater()
        self._fit_rows()
        self.changed.emit()

    def _fit_rows(self):
        self.scroll.setFixedHeight(min(3, max(1, len(self.rows))) * 48 + 4)
        for entry in self.rows:
            entry[3].setEnabled(len(self.rows) > 1)

    def intervals(self):
        intervals = []
        for _, beginning, ending, _ in self.rows:
            start, end = beginning.value(), ending.value()
            seconds = (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
            intervals.append({'started_at': start.isoformat(), 'ended_at': end.isoformat(), 'seconds': seconds})
        intervals.sort(key=lambda span: datetime.fromisoformat(span['started_at']).astimezone(timezone.utc))
        validate_work_intervals(intervals)
        return intervals


class WorkLogDialog(_InputDialog):
    """Confirm work periods, with a duration-only fallback for old records."""

    def __init__(self, project, log=None, initial_minutes=None, initial_date=None,
                 initial_task_id=None, parent=None, *, initial_intervals=None):
        super().__init__(
            'Edit time record' if log else 'Record time',
            'Adjust the start and end times. The duration and hourly chart follow these periods.',
            parent,
        )
        self.setMinimumWidth(680)
        self.resize(700, 570)
        self.form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        self.project, self.log = project, log
        self.date_edit = _date_input(log.worked_on if log else (initial_date or date.today()), project.start_date)
        self.date_edit.setMaximumDate(_qdate(date.today()))
        confirmed = log.work_intervals if log else initial_intervals
        self.legacy = log is not None and confirmed is None
        spans = confirmed
        if spans is None and log and log.focus_details:
            spans = log.focus_details['segments']
        if not spans:
            end = datetime.now().astimezone()
            if initial_date and initial_date != end.date():
                end = datetime.combine(initial_date, end.timetz())
            minimum = datetime.combine(project.start_date, datetime.min.time(), tzinfo=local_timezone())
            if self.legacy or initial_intervals is not None:
                start = end
            else:
                start = max(minimum, end - timedelta(minutes=initial_minutes or 25))
            spans = [{'started_at': start.isoformat(), 'ended_at': end.isoformat(),
                      'seconds': (end-start).total_seconds()}]
        self.period_editor = WorkPeriodEditor(spans, project.start_date)
        self.periods_check = QCheckBox('Set or correct the time periods')
        self.periods_check.setChecked(not self.legacy)
        self.periods_check.setVisible(self.legacy)
        self.duration_label = QLabel()
        self.duration_label.setObjectName('section')
        self.duration_hint = QLabel()
        self.duration_hint.setObjectName('muted')
        self.duration_hint.setWordWrap(True)
        self.task_combo = QComboBox()
        self.task_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.task_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.task_combo.setMinimumContentsLength(12)
        self.task_combo.addItem('The whole project', None)

        def add_tasks(tasks, path=()):
            for task in tasks:
                names = (*path, task.title)
                self.task_combo.addItem(' / '.join(names), task.id)
                add_tasks(task.children, names)
        add_tasks(project.tasks)
        selected = log.task_id if log else initial_task_id
        if selected:
            index = self.task_combo.findData(selected)
            if index >= 0:
                self.task_combo.setCurrentIndex(index)
        self.task_combo.setEnabled(log is None)
        self.note_edit = QTextEdit()
        self.note_edit.setAcceptRichText(False)
        self.note_edit.setPlainText(log.note if log else '')
        self.note_edit.setPlaceholderText('What did you work on? (optional)')
        self.note_edit.setFixedHeight(76)
        project_label = QLabel(project.title)
        project_label.setTextFormat(Qt.TextFormat.PlainText)
        project_label.setWordWrap(True)
        self.form.addRow('Project', project_label)
        self.form.addRow('Work date', self.date_edit)
        self.form.addRow('Task', self.task_combo)
        self.form.addRow(self.periods_check)
        self.form.addRow(self.period_editor)
        self.form.addRow('Recorded', self.duration_label)
        self.form.addRow(self.duration_hint)
        self.form.addRow('Note', self.note_edit)
        self._add_buttons('Save changes' if log else 'Save time record')
        self.period_editor.changed.connect(self._update_duration)
        self.periods_check.toggled.connect(self._update_duration)
        self._update_duration()
        if project.start_date > date.today():
            self._show_error('This project has not started yet. Record work from its start date.')
            self.save_button.setEnabled(False)

    def _update_duration(self, *args):
        use_periods = self.periods_check.isChecked()
        self.period_editor.setVisible(use_periods)
        self.form.setRowVisible(self.date_edit, not use_periods)
        visible_rows = min(3, max(1, len(self.period_editor.rows))) if use_periods else 1
        self.setMinimumHeight(570 + (visible_rows - 1) * 48)
        if not use_periods:
            self.duration_label.setText(f'{self.log.minutes} min · existing record')
            self.duration_hint.setText('This older record has no confirmed periods. Keep its minutes, or enable periods above to correct the actual start and end times.')
            return
        try:
            spans = self.period_editor.intervals()
            minutes = work_interval_minutes(spans)
            seconds = sum(span['seconds'] for span in spans)
            self.duration_label.setText(f'{minutes} min')
            previous = f'Previously recorded: {self.log.minutes} min. ' if self.legacy else ''
            if seconds < .001:
                exact = '<0.001s'
            elif seconds < 1:
                exact = f'{seconds:.3f}s'
            elif seconds < 60:
                exact = f'{seconds:.1f}s'
            else:
                exact = f'{seconds / 60:.2f} minutes'
            periods = 'period' if len(spans) == 1 else 'periods'
            self.duration_hint.setText(previous + f'{len(spans)} {periods} · {exact} of work. Partial minutes round up once per record; pauses between periods are excluded.')
        except ValueError as exc:
            self.duration_label.setText('Choose valid periods')
            self.duration_hint.setText(str(exc))

    def payload(self):
        values = {'note': self.note_edit.toPlainText().strip()}
        if self.periods_check.isChecked():
            spans = self.period_editor.intervals()
            values.update(work_intervals=spans, minutes=work_interval_minutes(spans),
                          worked_on=datetime.fromisoformat(spans[0]['started_at']).date())
        else:
            values.update(worked_on=self.date_edit.date().toPython(), minutes=self.log.minutes)
        if self.log is None:
            values['task_id'] = self.task_combo.currentData()
        return values

    def accept(self):
        try:
            values = self.payload()
            if not self.project.start_date <= values['worked_on'] <= date.today():
                raise ValueError('Choose a date between the project start and today.')
            now = datetime.now(timezone.utc)
            if any(datetime.fromisoformat(span['ended_at']).astimezone(timezone.utc) > now
                   for span in values.get('work_intervals', [])):
                raise ValueError('A work period cannot end in the future.')
        except ValueError as exc:
            self._show_error(str(exc))
            return
        super().accept()


class NoteDialog(_InputDialog):
    """Edit a note or project reflection."""

    def __init__(self, text="", parent=None, title="A note to yourself",
                 subtitle="Write a reminder or a short note."):
        super().__init__(title, subtitle, parent)
        self.note_edit = QTextEdit()
        self.note_edit.setAcceptRichText(False)
        self.note_edit.setPlainText(text)
        self.note_edit.setPlaceholderText(subtitle)
        self.note_edit.setMinimumHeight(160)
        self.text_edit = self.note_edit
        self.form.addRow(self.note_edit)
        self.count_label = QLabel()
        self.count_label.setObjectName("muted")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.layout_box.addWidget(self.count_label)
        self._add_buttons("Save note")
        self.note_edit.textChanged.connect(self._update_count)
        self._update_count()

    def _update_count(self):
        length = len(self.note_edit.toPlainText())
        self.count_label.setText(f"{length:,} / 1,000 characters")
        if length <= 1000:
            self.error_label.setVisible(False)

    def payload(self) -> str:
        return self.note_edit.toPlainText().strip()

    def accept(self):
        if len(self.note_edit.toPlainText()) > 1000:
            self._show_error("Please keep your note to 1,000 characters or fewer.")
            return
        super().accept()
