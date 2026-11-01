"""Saved project, task and work-record data."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from uuid import uuid4
import re

from .activity import validate_focus_details, validate_work_intervals, work_interval_minutes


def new_id() -> str:
    return str(uuid4())


def positive_minutes(value: int) -> None:
    # Reject bool, which is also an int in Python.
    if type(value) is not int or value <= 0:
        raise ValueError("Minutes must be a positive whole number.")


@dataclass
class TaskNode:
    title: str
    id: str = field(default_factory=new_id)
    completed: bool = False
    children: list[TaskNode] = field(default_factory=list)

    def find(self, task_id: str) -> TaskNode | None:
        """Find a task by searching this node and its children."""
        if self.id == task_id:
            return self
        for child in self.children:
            found = child.find(task_id)
            if found is not None:
                return found
        return None  # No match in this branch.

    def is_complete(self) -> bool:
        # Leaves store their status; stages use all child statuses.
        if not self.children:
            return self.completed
        return all(child.is_complete() for child in self.children)

    @classmethod
    def from_dict(cls, data: dict, depth: int = 2) -> TaskNode:
        if depth > 3:
            raise ValueError("Maximum depth is project -> stage -> task.")
        values = dict(data)
        values["children"] = [cls.from_dict(c, depth + 1) for c in values["children"]]
        return cls(**values)


@dataclass
class WorkLog:
    worked_on: date             # Work date confirmed by the user.
    minutes: int
    recorded_at: str            # Entry creation time, including its time zone.
    task_id: str | None = None  # None records work against the whole project.
    note: str = ""
    id: str = field(default_factory=new_id)
    source: str = "manual"     # 'focus' means confirmed from a focus session.
    focus_details: dict | None = None  # Captured intervals; older records use None.
    work_intervals: list[dict] | None = None  # Confirmed periods; never rewrite observations.

    def to_dict(self) -> dict:
        values = asdict(self)
        values["worked_on"] = self.worked_on.isoformat()
        return values

    @classmethod
    def from_dict(cls, data: dict) -> WorkLog:
        values = dict(data)
        values["worked_on"] = date.fromisoformat(values["worked_on"])
        return cls(**values)


@dataclass
class Project:
    title: str
    start_date: date
    deadline: date | None       # None means an ongoing daily goal.
    planned_minutes: int        # Original total estimate, fixed after creation.
    daily_minutes: int          # Usual daily target.
    daily_limit_minutes: int    # Per-project suggestion limit.
    color: str = "#7C83C4"
    motivation: str = ""
    note: str = ""
    image_path: str | None = None
    related_project_id: str | None = None
    id: str = field(default_factory=new_id)
    tasks: list[TaskNode] = field(default_factory=list)
    logs: list[WorkLog] = field(default_factory=list)
    outcome_completed: bool = False
    archived_at: str | None = None
    catch_up_enabled: bool = True  # Keeps the policy used by older saves.

    def find_task(self, task_id: str) -> TaskNode:
        for task in self.tasks:
            found = task.find(task_id)
            if found is not None:
                return found
        raise ValueError("Task does not belong to this project.")

    def to_dict(self) -> dict:
        values = asdict(self)
        values["start_date"] = self.start_date.isoformat()
        values["deadline"] = self.deadline.isoformat() if self.deadline is not None else None
        values["logs"] = [log.to_dict() for log in self.logs]
        return values

    @classmethod
    def from_dict(cls, data: dict) -> Project:
        values = dict(data)
        values["start_date"] = date.fromisoformat(values["start_date"])
        values["deadline"] = date.fromisoformat(values["deadline"]) if values["deadline"] is not None else None
        values["tasks"] = [TaskNode.from_dict(t) for t in values["tasks"]]
        values["logs"] = [WorkLog.from_dict(log) for log in values["logs"]]
        project = cls(**values)
        validate_project(project)
        return project


def validate_project(project: Project) -> None:
    if not isinstance(project.title, str) or not project.title.strip():
        raise ValueError("Project title cannot be empty.")
    if type(project.start_date) is not date or (project.deadline is not None and type(project.deadline) is not date):
        raise ValueError("Use a start date and an optional deadline.")
    if project.deadline is not None and project.deadline < project.start_date:
        raise ValueError("Deadline cannot be before the start date.")
    if type(project.catch_up_enabled) is not bool:
        raise ValueError("Catch-up must be enabled or disabled.")
    for value in (project.planned_minutes, project.daily_minutes, project.daily_limit_minutes):
        positive_minutes(value)
    if project.daily_limit_minutes < project.daily_minutes:
        raise ValueError("Daily limit cannot be below the preferred daily effort.")
    if not isinstance(project.color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", project.color):
        raise ValueError("Use a colour such as #7C83C4.")
    if type(project.outcome_completed) is not bool:
        raise ValueError("Outcome status must be True or False.")
    for value in (project.motivation, project.note):
        if not isinstance(value, str):
            raise ValueError("Motivation and note must be text.")
    for value in (project.image_path, project.related_project_id, project.archived_at):
        if value is not None and not isinstance(value, str):
            raise ValueError("Optional project references must be text or None.")
    task_ids = set()

    def visit(nodes: list[TaskNode], depth: int) -> None:
        if not isinstance(nodes, list):
            raise ValueError("Tasks must be a list of task nodes.")
        for node in nodes:
            if not isinstance(node, TaskNode):
                raise ValueError("Each task must be a task node.")
            if depth > 3:
                raise ValueError("Maximum depth is project -> stage -> task.")
            if not node.id or node.id in task_ids:
                raise ValueError("A task cannot occur twice or contain itself.")
            task_ids.add(node.id)
            if not isinstance(node.title, str) or not node.title.strip():
                raise ValueError("Task title cannot be empty.")
            if type(node.completed) is not bool:
                raise ValueError("Task status must be True or False.")
            visit(node.children, depth + 1)

    visit(project.tasks, 2)  # The project itself counts as level 1.
    log_ids = set()
    for log in project.logs:
        positive_minutes(log.minutes)
        if not log.id or log.id in log_ids:
            raise ValueError("Duplicate or empty work-log ID.")
        log_ids.add(log.id)
        if type(log.worked_on) is not date or log.worked_on < project.start_date:
            raise ValueError("Work cannot predate the project.")
        if log.task_id is not None and log.task_id not in task_ids:
            raise ValueError("A work log refers to a missing task.")
        if not isinstance(log.note, str):
            raise ValueError("Work-log note must be text.")
        if not isinstance(log.source, str) or log.source not in ("manual", "focus"):
            raise ValueError("Work-log source must be 'manual' or 'focus'.")
        if log.focus_details is not None and log.source != "focus":
            raise ValueError("Only focus-session records can include observed activity.")
        validate_focus_details(log.focus_details)
        if log.work_intervals is not None:
            periods = validate_work_intervals(log.work_intervals)
            if periods[0][0].date() != log.worked_on:
                raise ValueError("The work date must match the first work period.")
            if any(start.date() < project.start_date for start, _, _ in periods):
                raise ValueError("Work periods cannot predate the project.")
            if log.minutes != work_interval_minutes(log.work_intervals):
                raise ValueError("Recorded minutes must match the work periods.")
        if datetime.fromisoformat(log.recorded_at).tzinfo is None:
            raise ValueError("Entry timestamps must include a time zone.")
