"""Daily suggestions and optional catch-up explanations."""

from datetime import date

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from planner.planning import recovery_summary


def _label(text, role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


class RecoveryBar(QWidget):
    """Show the usual and extra parts of the suggested time."""

    def __init__(self, baseline, extra, parent=None):
        super().__init__(parent)
        self.baseline, self.extra = baseline, extra
        self.setFixedHeight(12)
        self.setAccessibleName(f"{baseline} usual minutes and {extra} additional catch-up minutes")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        total = self.baseline + self.extra
        if not total:
            painter.end()
            return
        painter.setPen(Qt.PenStyle.NoPen)
        width = self.width() * self.baseline / total
        painter.setBrush(QColor("#718479"))
        painter.drawRoundedRect(QRectF(0, 3, self.width(), 6), 3, 3)
        if self.extra:
            painter.setBrush(QColor("#BB9877"))
            painter.drawRoundedRect(QRectF(width, 3, self.width() - width, 6), 3, 3)
        painter.end()


def _copy(summary):
    status = summary["status"]
    if status == "archived":
        return "Archived project", "Reopen this project to see daily suggestions."
    if status == "effort_covered":
        return "Time target reached", "Recorded time has reached the original estimate. Mark the outcome separately."
    if status == "upcoming":
        return "Not started yet", "Daily suggestions begin on the project's start date."
    if status == "overdue":
        return "Deadline passed", "Review the deadline or daily target to continue planning."
    if status == "today_recorded":
        return "Today's target recorded", "No more time is suggested today. The plan continues on the following days."
    if status == "capacity_pressure":
        return "More time is needed", "Some work does not fit before the deadline at this pace. Review the deadline or daily target."
    if status == "catch_up_off":
        return "Usual daily target", "Catch-up is off. Missed days do not increase today's target."
    if status == "ongoing":
        return "Daily goal", "This goal has no deadline. Today's target and total recorded time are tracked separately."
    if status == "gentle_adjustment":
        extra = summary["today_catch_up_minutes"]
        days = summary["days_remaining"]
        if summary["ongoing"]:
            return "Today's catch-up", f"Yesterday's shortfall adds {extra} min today. Earlier missed days are not carried over."
        return "Adjusted daily target", f"The remaining time is spread across {days} days, with {extra} extra min suggested today."
    if summary["unrecorded_minutes"]:
        return "Keep your usual pace", "There is unrecorded earlier effort, but the remaining days still allow your usual pace."
    return "Your usual pace", "Today's suggestion fits your usual pace. It updates when you record time."


def build_recovery_card(window, project, compact=True):
    """Build a catch-up summary from the current work records."""
    today = window.service.today()
    summary = recovery_summary(project, today)
    card = QFrame()
    card.setObjectName("subcard")
    card.setProperty("recoveryStatus", summary["status"])
    card.summary = summary
    layout = QVBoxLayout(card)
    layout.setContentsMargins(12, 8 if compact else 12, 12, 8 if compact else 12)
    layout.setSpacing(6)
    heading, explanation = _copy(summary)
    card.heading_label = _label(heading, "section")
    layout.addWidget(card.heading_label)
    if summary["status"] not in ("archived", "effort_covered", "upcoming", "overdue"):
        usual = summary["today_baseline_minutes"]
        extra = summary["today_catch_up_minutes"]
        target = summary["today_target_minutes"]
        if summary["status"] == "today_recorded":
            equation = f"{summary['today_recorded_minutes']} min recorded today · no extra suggestion"
        else:
            equation = f"{usual} min usual + {extra} min extra = {target} min today" if extra else f"{target} min suggested today"
        card.equation_label = _label(equation)
        layout.addWidget(card.equation_label)
        if compact:
            if summary["yesterday_gap_minutes"]:
                detail = (f"Yesterday: {summary['yesterday_recorded_minutes']} min recorded (usual {summary['yesterday_target_minutes']}). "
                          f"Today: {summary['today_additional_minutes']} min left.")
            else:
                ending = "no deadline" if summary["ongoing"] else f"{summary['days_remaining']} days remaining"
                detail = f"{summary['today_additional_minutes']} min left today · {ending}."
            card.explanation_label = _label(detail, "muted")
            card.explanation_label.setParent(card)
            card.explanation_label.hide()
            card.setToolTip(explanation + "\n" + detail)
            return card
        if not compact and summary["status"] != "today_recorded":
            layout.addWidget(RecoveryBar(usual, extra))
        if summary["yesterday_target_minutes"] and (summary["yesterday_gap_minutes"] or not compact):
            gap = summary["yesterday_gap_minutes"]
            layout.addWidget(_label(
                f"Yesterday: {summary['yesterday_target_minutes']} min usual pace · "
                f"{summary['yesterday_recorded_minutes']} min recorded · {gap} min unrecorded.",
                "muted"))
        if summary["today_recorded_minutes"] or not compact:
            layout.addWidget(_label(
                f"Already recorded today: {summary['today_recorded_minutes']} min. "
                f"Still to record: {summary['today_additional_minutes']} min.", "muted"))
    card.explanation_label = _label(explanation, "muted")
    layout.addWidget(card.explanation_label)
    if not compact:
        layout.addWidget(_label(
            (f"Catch-up: on · at most {summary['gentle_increase_limit_minutes']} extra min/day. " if project.catch_up_enabled else "Catch-up: off. ") +
            f"Daily cap: {project.daily_limit_minutes} min. Backfill actual work to recalculate.", "muted"))
    return card


class DailyPlanPage(QWidget):
    """Page through daily suggestions without a scrolling list."""
    def __init__(self, window, project):
        super().__init__()
        self.window, self.project = window, project
        self.schedule = window.service.schedule(project.id)
        self.page_index = 0
        self.page_size = 2
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        self.recovery_card = build_recovery_card(window, project, compact=True)
        layout.addWidget(self.recovery_card)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(4)
        layout.addLayout(self.rows)
        controls = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.page_label = _label("", "muted")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.page_label, 1)
        controls.addWidget(self.next_button)
        self.previous_button.clicked.connect(lambda: self.change_page(-1))
        self.next_button.clicked.connect(lambda: self.change_page(1))
        layout.addLayout(controls)
        if self.schedule["unscheduled_minutes"]:
            layout.addWidget(_label(f"{self.schedule['unscheduled_minutes']} min outside the available plan. Review the deadline or daily pace.", "error"))
        layout.addStretch()
        self.render_rows()

    def change_page(self, direction):
        count = max(1, (len(self.schedule["days"]) + self.page_size - 1) // self.page_size)
        self.page_index = min(max(self.page_index + direction, 0), count - 1)
        self.render_rows()

    def render_rows(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        first = self.page_index * self.page_size
        entries = self.schedule["days"][first:first + self.page_size]
        for day in entries:
            on = date.fromisoformat(day["date"])
            recorded = sum(log.minutes for log in self.project.logs if log.worked_on == on)
            total = recorded + day["additional_minutes"]
            row = QFrame()
            row.setObjectName("subcard")
            line = QHBoxLayout(row)
            line.setContentsMargins(10, 7, 10, 7)
            prefix = "Today" if on == self.window.service.today() else on.strftime("%a, %d %b")
            line.addWidget(_label(prefix), 1)
            extra = max(total - self.project.daily_minutes, 0) if day["additional_minutes"] else 0
            annotation = f"{day['additional_minutes']} min left"
            if extra:
                annotation += f" · +{extra} extra"
            line.addWidget(_label(annotation, "muted"))
            self.rows.addWidget(row)
        if not entries:
            self.rows.addWidget(_label("No daily suggestions for this date.", "muted"))
        count = max(1, (len(self.schedule["days"]) + self.page_size - 1) // self.page_size)
        suffix = " · next 7 days" if self.project.deadline is None else ""
        self.page_label.setText(f"{self.page_index + 1} / {count}{suffix}")
        self.previous_button.setEnabled(self.page_index > 0)
        self.next_button.setEnabled(self.page_index + 1 < count)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        desired = 4 if self.height() >= 440 else 2
        if desired != self.page_size:
            first = self.page_index * self.page_size
            self.page_size = desired
            self.page_index = first // desired
            self.render_rows()


def build_daily_plan(window, project):
    return DailyPlanPage(window, project)
