"""Project, record and note forms. Saving is handled by the caller."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSizePolicy, QTabWidget, QTextEdit, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from planner.models import TaskNode

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

    def _update_deadline_mode(self, *args):
        ongoing = self.no_deadline_check.isChecked()
        self.deadline_edit.setVisible(not ongoing)
        self.form.setRowVisible(self.planned_minutes, not ongoing)
        if hasattr(self, "fixed_hint"):
            self.fixed_hint.setVisible(not ongoing)
        self.no_deadline_check.setToolTip("An ongoing goal uses your daily target, without a finish date or a total-effort limit.")

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


class WorkLogDialog(_InputDialog):
    """Enter or correct a work record."""

    def __init__(self, project, log=None, initial_minutes=None, initial_date=None,
                 initial_task_id=None, parent=None):
        super().__init__(
            "Edit time record" if log else "Record time",
            "Choose the day and minutes you actually worked.",
            parent,
        )
        self.project = project
        self.log = log
        self.date_edit = _date_input(
            log.worked_on if log else (initial_date or date.today()), project.start_date
        )
        self.date_edit.setMaximumDate(_qdate(date.today()))
        self.minutes_edit = _minutes(log.minutes if log else (initial_minutes or 25))
        self.task_combo = QComboBox()
        self.task_combo.addItem("The whole project", None)

        def add_tasks(tasks, path=()):
            for task in tasks:
                names = (*path, task.title)
                self.task_combo.addItem(" / ".join(names), task.id)
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
        self.note_edit.setPlainText(log.note if log else "")
        self.note_edit.setPlaceholderText("What did you work on? (optional)")
        self.note_edit.setFixedHeight(100)
        project_label = QLabel(project.title)
        project_label.setTextFormat(Qt.TextFormat.PlainText)
        project_label.setWordWrap(True)
        self.form.addRow("Project", project_label)
        self.form.addRow("Actual work date", self.date_edit)
        self.form.addRow("Time spent", self.minutes_edit)
        self.form.addRow("Task", self.task_combo)
        task_hint = QLabel("Task time includes its subtasks. Each record counts once towards the project.")
        task_hint.setObjectName("muted")
        task_hint.setWordWrap(True)
        self.form.addRow("", task_hint)
        self.form.addRow("Note", self.note_edit)
        self._add_buttons("Save changes" if log else "Save time record")
        if project.start_date > date.today():
            self._show_error("This project has not started yet. Work can be recorded from its start date.")
            self.save_button.setEnabled(False)

    def payload(self) -> dict:
        values = {
            "worked_on": self.date_edit.date().toPython(),
            "minutes": self.minutes_edit.value(),
            "note": self.note_edit.toPlainText().strip(),
        }
        if self.log is None:
            values["task_id"] = self.task_combo.currentData()
        return values

    def accept(self):
        try:
            self.minutes_edit.interpretText()
            values = self.payload()
        except ValueError as exc:
            self._show_error(str(exc))
            self.minutes_edit.setFocus()
            return
        if not self.project.start_date <= values["worked_on"] <= date.today():
            self._show_error("Choose a date between the project start and today.")
            return
        if values["minutes"] <= 0:
            self._show_error("Record at least one minute of actual work.")
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
