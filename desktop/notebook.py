"""Notebook pages for tasks, daily plans and time records."""

from datetime import datetime, timezone

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView, QListWidget, QListWidgetItem,
    QMenu, QStackedWidget, QTabBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .daily_plan import build_daily_plan, build_recovery_card
from .record_stats import RecordStatsPanel
from planner.statistics import local_timezone, recorded_minutes_on


def _record_span(start, end, *, dates=False):
    """Keep short intervals visibly different, down to fractions if needed."""
    dates = dates or start.date() != end.date()
    elapsed = (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
    seconds = bool(start.second or end.second or start.microsecond or end.microsecond
                   or elapsed < 60)
    fraction = 0
    if 0 < elapsed < 1 and start.replace(microsecond=0) == end.replace(microsecond=0):
        fraction = 3 if start.microsecond // 1000 != end.microsecond // 1000 else 6

    def stamp(value):
        text = value.strftime(("%d %b " if dates else "") + ("%H:%M:%S" if seconds else "%H:%M"))
        if fraction:
            text += "." + f"{value.microsecond:06d}"[:fraction]
        if start.utcoffset() != end.utcoffset():
            offset = value.strftime("%z")
            text += " " + offset[:3] + ":" + offset[3:]
        return text

    return stamp(start) + "–" + stamp(end)


def _local_spans(intervals):
    zone = local_timezone()
    return [(datetime.fromisoformat(span["started_at"].replace("Z", "+00:00")).astimezone(zone),
             datetime.fromisoformat(span["ended_at"].replace("Z", "+00:00")).astimezone(zone))
            for span in intervals]


class _TaskTree(QTreeWidget):
    """Draw branch controls with the same contrast as the task text."""

    def drawBranches(self, painter, rect, index):
        item = self.itemFromIndex(index)
        if item is None or not item.childCount():
            return
        x = rect.right() - self.indentation() / 2 + 1
        y = rect.center().y()
        arrow = QPainterPath()
        if item.isExpanded():
            arrow.moveTo(x - 4, y - 2)
            arrow.lineTo(x, y + 2)
            arrow.lineTo(x + 4, y - 2)
        else:
            arrow.moveTo(x - 2, y - 4)
            arrow.lineTo(x + 2, y)
            arrow.lineTo(x - 2, y + 4)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Text), 1.6,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(arrow)
        painter.restore()


class TaskPages(QWidget):
    def __init__(self, window, project):
        super().__init__()
        from .window import button, duration, label, row
        self.window = window
        self.page = getattr(window, "_task_page", 0)
        self.capacity = 5
        self._paging = False
        self._fit_pending = False
        collapsed = getattr(window, "_collapsed_task_ids", {})
        window._collapsed_task_ids = collapsed
        self.collapsed_ids = collapsed.setdefault(project.id, set())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(row(button("+ Task", window.add_task), button("+ Subtask", window.add_subtask),
                             button("Rename", window.rename_task, "ghost"), button("Delete", window.delete_task, "ghost")))
        layout.addWidget(label("Select a name to focus. Tick a box to mark a step complete.", "muted", True))
        self.tree = _TaskTree()
        self.tree.setIndentation(22)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Task", "Recorded"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setStretchLastSection(False)
        self.tree.setMinimumHeight(64)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setAccessibleName("Project tasks")
        self.tree.viewport().installEventFilter(self)
        self.tree.installEventFilter(self)
        window.task_tree = self.tree

        direct = {}
        for log in project.logs:
            direct[log.task_id] = direct.get(log.task_id, 0) + log.minutes
        totals = {}

        def total(node):
            totals[node.id] = direct.get(node.id, 0) + sum(total(child) for child in node.children)
            return totals[node.id]

        for node in project.tasks:
            total(node)

        def add_nodes(nodes, parent=None):
            for node in nodes:
                recorded = totals[node.id]
                item = QTreeWidgetItem([node.title, duration(recorded) + (" total" if node.children else "")])
                item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                item.setToolTip(0, node.title)
                own = direct.get(node.id, 0)
                item.setToolTip(1, f"Direct: {duration(own)}\nSubtasks: {duration(recorded - own)}\nTotal: {duration(recorded)}\nEach record counts once towards the project.")
                item.setData(0, Qt.ItemDataRole.UserRole, node.id)
                item.setData(0, Qt.ItemDataRole.UserRole + 1, bool(node.children))
                if node.children:
                    item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                    item.setText(0, ("✓  " if node.is_complete() else "◦  ") + node.title)
                else:
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.CheckState.Checked if node.completed else Qt.CheckState.Unchecked)
                (self.tree.addTopLevelItem if parent is None else parent.addChild)(item)
                add_nodes(node.children, item)

        add_nodes(project.tasks)
        self.tree.expandAll()
        for item in self.items():
            if item.data(0, Qt.ItemDataRole.UserRole) in self.collapsed_ids:
                item.setExpanded(False)
        self.tree.itemChanged.connect(window.toggle_task)
        self.tree.itemExpanded.connect(self.branch_changed)
        self.tree.itemCollapsed.connect(self.branch_changed)
        layout.addWidget(self.tree, 1)
        pager = QHBoxLayout()
        self.previous = button("←", lambda: self.move(-1), "ghost")
        self.next = button("→", lambda: self.move(1), "ghost")
        self.previous.setAccessibleName("Previous tasks")
        self.next.setAccessibleName("Next tasks")
        self.counter = label("", "muted")
        pager.addWidget(self.previous)
        pager.addWidget(self.counter)
        pager.addWidget(self.next)
        pager.addStretch()
        layout.addLayout(pager)
        layout.addWidget(button("Focus on selected task  →", window.focus_selected_task, "primary"))
        self.repage()

    def items(self, expanded_only=False):
        result = []
        def visit(item):
            result.append(item)
            if not expanded_only or item.isExpanded():
                for index in range(item.childCount()):
                    visit(item.child(index))
        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))
        return result

    def repage(self, *args):
        if self._paging:
            return
        self._paging = True
        try:
            rows = self.items(expanded_only=True)
            pages = max(1, (len(rows) + self.capacity - 1) // self.capacity)
            self.page = min(max(self.page, 0), pages - 1)
            visible = rows[self.page*self.capacity:(self.page+1)*self.capacity]
            keep = set(id(item) for item in visible)
            # Keep ancestors visible so each child still has its task context.
            for item in visible:
                parent = item.parent()
                while parent is not None:
                    keep.add(id(parent))
                    parent = parent.parent()
            for item in self.items():
                parent = item.parent()
                while parent is not None and parent.isExpanded():
                    parent = parent.parent()
                # Collapsing is Qt's job; hidden flags are only for pagination.
                item.setHidden(parent is None and id(item) not in keep)
            self.previous.setEnabled(self.page > 0)
            self.next.setEnabled(self.page < pages - 1)
            self.counter.setText(f"{self.page+1} / {pages}" if rows else "No tasks yet")
            self.window._task_page = self.page
            current = self.tree.currentItem()
            if current is not None and id(current) not in keep:
                self.tree.clearSelection()
                self.tree.setCurrentItem(None)
        finally:
            self._paging = False

    def branch_changed(self, item):
        task_id = item.data(0, Qt.ItemDataRole.UserRole)
        if item.isExpanded():
            self.collapsed_ids.discard(task_id)
        else:
            self.collapsed_ids.add(task_id)
        rows = self.items(expanded_only=True)
        if item in rows:
            self.page = rows.index(item) // self.capacity
        self.repage()

    def move(self, direction):
        self.page += direction
        self.repage()
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)

    def select_task(self, task_id):
        """Reveal a newly added task while keeping its parent in view."""
        item = next((item for item in self.items() if item.data(0, Qt.ItemDataRole.UserRole) == task_id), None)
        if item is None:
            return
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()
        self.page = self.items(expanded_only=True).index(item) // self.capacity
        self.repage()
        self.tree.setCurrentItem(item)
        self.tree.setFocus()

    def queue_fit(self):
        if not self._fit_pending:
            self._fit_pending = True
            # Measure rows after Qt has finished the current layout pass.
            QTimer.singleShot(0, self, self.fit_capacity)

    def fit_capacity(self):
        self._fit_pending = False
        heights = [self.tree.sizeHintForIndex(self.tree.indexFromItem(item)).height()
                   for item in self.items() if not item.isHidden()]
        row_height = max([self.tree.fontMetrics().height() + 18] + heights)
        capacity = max(1, (self.tree.viewport().height() - 6) // row_height - 1)
        if capacity != self.capacity:
            current = self.tree.currentItem()
            self.capacity = capacity
            rows = self.items(expanded_only=True)
            if current in rows:
                self.page = rows.index(current) // capacity
            self.repage()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.queue_fit()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.queue_fit()


class RecordPages(QWidget):
    def __init__(self, window, project, *, show_add_button=True):
        super().__init__()
        from .window import button, label, row
        self.window = window
        self.records = sorted(project.logs, key=lambda log: (log.worked_on, log.recorded_at), reverse=True)
        self.page, self.capacity = getattr(window, "_log_page", 0), 4
        self._fit_pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        self.listing = QListWidget()
        self.listing.setMinimumHeight(64)
        self.listing.setWordWrap(True)
        self.listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.viewport().installEventFilter(self)
        self.listing.installEventFilter(self)
        self.listing.itemDoubleClicked.connect(lambda item: window.edit_work())
        window.logs_list = self.listing
        layout.addWidget(self.listing, 1)
        pagination = QHBoxLayout()
        self.previous = button("←", lambda: self.move(-1), "ghost")
        self.next = button("→", lambda: self.move(1), "ghost")
        self.counter = label("", "muted")
        for widget in (self.previous, self.counter, self.next):
            pagination.addWidget(widget)
        pagination.addStretch()
        layout.addLayout(pagination)
        actions = row(button("Edit", window.edit_work), button("Delete", window.delete_work, "ghost"))
        if show_add_button:
            window.add_work_button = button("+ Record time", window.add_work, "primary")
            actions.insertWidget(0, window.add_work_button)
        layout.addLayout(actions)
        undo = button("Undo last record change", lambda: window.operate(window.service.undo_last_work_change, "Last record change undone."), "ghost")
        undo.setEnabled(window.service.can_undo_work_change())
        layout.addWidget(undo)
        self.repage()

    def repage(self):
        from .window import duration
        selected = self.listing.currentItem()
        selected_id = selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.listing.clear()
        pages = max(1, (len(self.records) + self.capacity - 1) // self.capacity)
        self.page = min(max(self.page, 0), pages - 1)
        for log in self.records[self.page*self.capacity:(self.page+1)*self.capacity]:
            details = log.focus_details
            tooltip = [log.note] if log.note else []
            intervals = getattr(log, "work_intervals", None)
            if intervals:
                spans = _local_spans(intervals)
                description = _record_span(spans[0][0], spans[-1][1])
                if len(spans) > 1:
                    description += f" · {len(spans)} intervals"
                tooltip.append("Recorded intervals (pauses excluded):\n" + "\n".join(
                    _record_span(start, end, dates=True) for start, end in spans))
                tooltip.append("Calculated work total: " + duration(log.minutes))
            elif details and details["segments"]:
                spans = _local_spans(details["segments"])
                description = "Captured " + _record_span(spans[0][0], spans[-1][1])
                if len(spans) > 1:
                    description += f" · {len(spans)} intervals"
                tooltip.append("Original timer intervals (pauses excluded):\n" + "\n".join(
                    _record_span(start, end, dates=True) for start, end in spans))
                tooltip.append("Stored work total: " + duration(log.minutes))
                if abs(log.minutes * 60 - details["measured_seconds"]) > 60:
                    tooltip.append("The stored total differs from the captured timer. Edit the time intervals to recalculate it.")
            else:
                description = "No time range saved · edit to add one"
            if details and details["music"]:
                tooltip.append("Captured music (original timer):\n" + "\n".join(dict.fromkeys(
                    song["title"] + (" — " + song["artist"] if song["artist"] else "") for song in details["music"])))
            note = self.listing.fontMetrics().elidedText(description, Qt.TextElideMode.ElideRight,
                                                        max(40, self.listing.viewport().width() - 24))
            item = QListWidgetItem(f"{log.worked_on.strftime('%d %b')}  ·  {duration(log.minutes)}" + ("\n" + note if note else ""))
            item.setData(Qt.ItemDataRole.UserRole, log.id)
            item.setToolTip("\n\n".join(tooltip) or description)
            item.setSizeHint(QSize(0, 58))
            self.listing.addItem(item)
            if log.id == selected_id:
                self.listing.setCurrentItem(item)
        self.counter.setText(f"{self.page+1} / {pages}" if self.records else "No records yet")
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled(self.page < pages - 1)
        self.window._log_page = self.page

    def move(self, direction):
        self.page += direction
        self.repage()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.queue_fit()

    def queue_fit(self):
        if not self._fit_pending:
            self._fit_pending = True
            QTimer.singleShot(0, self, self.fit_capacity)

    def fit_capacity(self):
        self._fit_pending = False
        capacity = max(1, (self.listing.viewport().height() - 4) // 58)
        self.capacity = capacity
        self.repage()

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self.queue_fit()
        return super().eventFilter(watched, event)


class RecordsWorkspace(QWidget):
    """Switch between the daily chart and editable time records."""
    def __init__(self, window, project):
        super().__init__()
        from .window import button
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)
        choices = QHBoxLayout()
        self.modes = QButtonGroup(self)
        self.overview_button = button("Overview", lambda: None, "recordMode")
        self.entries_button = button("Entries", lambda: None, "recordMode")
        for index, control in enumerate((self.overview_button, self.entries_button)):
            control.setCheckable(True)
            self.modes.addButton(control, index)
            choices.addWidget(control)
        choices.addStretch()
        window.add_work_button = button("+ Record time", window.add_work, "ghost")
        window.add_work_button.setStyleSheet("padding: 5px 9px;")
        choices.addWidget(window.add_work_button)
        layout.addLayout(choices)
        self.stack = QStackedWidget()
        self.statistics = RecordStatsPanel(window, project, self)
        self.entries = RecordPages(window, project, show_add_button=False)
        window.record_stats = self.statistics
        window.record_pages = self.entries
        self.stack.addWidget(self.statistics)
        self.stack.addWidget(self.entries)
        layout.addWidget(self.stack, 1)
        self.modes.idClicked.connect(self.set_mode)
        self.set_mode(getattr(window, "_records_mode", 0))

    def set_mode(self, mode):
        mode = 1 if mode == 1 else 0
        self.window._records_mode = mode
        self.stack.setCurrentIndex(mode)
        self.modes.button(mode).setChecked(True)


def build_notebook(window):
    from .window import EffortBar, button, duration, fit_combo, label
    content = window.make_panel("Notebook", "", flat=True)
    content.setSpacing(12)
    window.notebook_motivation = None
    active = [project for project in window.service.list_projects() if project.archived_at is None]
    window.new_project_button = button("+ New project", window.new_project, "primary")
    if not active:
        content.addWidget(label("No projects yet.", "section"))
        content.addWidget(label("Create a project with a deadline or an ongoing daily goal.", "muted", True))
        content.addWidget(window.new_project_button, alignment=Qt.AlignmentFlag.AlignLeft)
        content.addStretch()
        return
    if window.selected_project_id not in {project.id for project in active}:
        window.selected_project_id = active[0].id
    project = window.selected_project()
    controls = QHBoxLayout()
    window.project_combo = QComboBox()
    fit_combo(window.project_combo)
    for choice in active:
        window.project_combo.addItem(choice.title, choice.id)
    window.project_combo.setCurrentIndex(window.project_combo.findData(project.id))
    window.project_combo.setToolTip(project.motivation)
    window.project_combo.currentIndexChanged.connect(window.select_project)
    controls.addWidget(window.project_combo, 1)
    controls.addWidget(window.new_project_button)
    window.edit_project_button = button("Edit goal", window.edit_project, "ghost")
    window.edit_project_button.setToolTip("Date, daily pace and catch-up preference")
    controls.addWidget(window.edit_project_button)
    options = button("···", lambda: None, "ghost")
    options.setAccessibleName("Project options")
    menu = QMenu(options)
    menu.addAction("Book cover and position", lambda: window.edit_books(project.id))
    menu.addAction("Change picture" if project.image_path else "Add picture", window.import_picture)
    menu.addSeparator()
    menu.addAction("Archive project", window.archive_project)
    options.setMenu(menu)
    controls.addWidget(options)
    content.addLayout(controls)

    # A separate tab bar stays in place when Records hides the summary.
    workspace = QVBoxLayout()
    workspace.setSpacing(0)
    tabs = QTabBar(window.panel)
    tabs.setObjectName("notebookTabs")
    tabs.setAccessibleName("Notebook sections")
    tabs.setExpanding(False)
    tabs.setDrawBase(False)
    tabs.setUsesScrollButtons(False)
    for title in ("Tasks", "Daily plan", "Records"):
        tabs.addTab(title)
    window.plan_tabs = tabs
    workspace.addWidget(tabs, alignment=Qt.AlignmentFlag.AlignLeft)
    board = QHBoxLayout()
    board.setSpacing(18)
    summary = QWidget(window.panel)
    window.notebook_summary = summary
    summary.setFixedWidth(198)
    stats = QVBoxLayout(summary)
    stats.setContentsMargins(0, 4, 0, 0)
    stats.setSpacing(10)
    total = window.service.progress(project.id)["actual_minutes"]
    if project.deadline is None:
        today = sum(recorded_minutes_on(log, window.service.today()) for log in project.logs)
        window.effort_bar = EffortBar(today, project.daily_minutes, project.color, caption="TODAY'S RHYTHM", lifetime=total)
    else:
        window.effort_bar = EffortBar(total, project.planned_minutes, project.color)
    stats.addWidget(window.effort_bar)
    due = "Ongoing · no deadline" if project.deadline is None else "Due " + project.deadline.strftime("%d %b %Y")
    stats.addWidget(label(due, "muted", True))
    window.outcome_check = QCheckBox("Outcome achieved")
    window.outcome_check.setChecked(project.outcome_completed)
    window.outcome_check.setToolTip("Recorded time and the outcome are tracked separately.")
    window.outcome_check.toggled.connect(window.toggle_outcome)
    stats.addWidget(window.outcome_check)
    if project.motivation:
        reason = project.motivation if len(project.motivation) < 72 else project.motivation[:69] + "…"
        hint = label(reason, "muted", True)
        hint.setToolTip(project.motivation)
        window.notebook_motivation = hint
        stats.addWidget(hint)
        hint.setVisible(window.height() >= 820)
    mode = "Gentle catch-up on" if project.catch_up_enabled else "Your usual pace · catch-up off"
    stats.addWidget(label(mode, "muted", True))
    window.recovery_card = build_recovery_card(window, project, compact=True)
    stats.addWidget(window.recovery_card)
    stats.addStretch()
    board.addWidget(summary)
    stack = QStackedWidget(window.panel)
    stack.setMinimumWidth(0)
    window.notebook_stack = stack
    window.task_pages = TaskPages(window, project)
    stack.addWidget(window.task_pages)
    stack.addWidget(build_daily_plan(window, project))
    window.records_workspace = RecordsWorkspace(window, project)
    stack.addWidget(window.records_workspace)
    board.addWidget(stack, 1)
    workspace.addLayout(board, 1)
    content.addLayout(workspace, 1)
    tabs.currentChanged.connect(stack.setCurrentIndex)
    tabs.currentChanged.connect(window._plan_tab_changed)
    tabs.setCurrentIndex(min(window._plan_tabs_index, tabs.count() - 1))
    stack.setCurrentIndex(tabs.currentIndex())
    window._plan_tab_changed(tabs.currentIndex())
