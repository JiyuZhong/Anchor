"""Project, task and work-record operations with validated saves."""

from copy import deepcopy
from datetime import date, datetime, timezone

from .models import Project, TaskNode, WorkLog, validate_project
from .activity import validate_work_intervals, work_interval_minutes
from .planning import suggest_schedule, task_minutes, time_bar
from .statistics import local_timezone, recorded_minutes_on
from .storage import JsonRepository


# Omitting periods during an edit keeps the record's current periods.
_UNCHANGED = object()


class PlannerService:
    """Apply one user action, validate it, then save it before changing memory."""

    def __init__(self, repository: JsonRepository, today=date.today):
        self.repository = repository
        self.today = today
        state = repository.load()
        projects = [Project.from_dict(p) for p in state["projects"]]
        self._projects = {p.id: p for p in projects}
        if len(projects) != len(self._projects):
            raise ValueError("Duplicate project IDs in save file.")
        for project in projects:
            if project.related_project_id is not None and project.related_project_id not in self._projects:
                raise ValueError("Related project does not exist.")
        self._last_log_change = state.get("last_log_change")
        # Load old undo snapshots through the same defaults as current records.
        if self._last_log_change is not None:
            for name in ("before", "after"):
                snapshot = self._last_log_change[name]
                if snapshot is not None:
                    self._last_log_change[name] = WorkLog.from_dict(snapshot).to_dict()

    def get_project(self, project_id: str) -> Project:
        if project_id not in self._projects:
            raise ValueError("Project not found.")
        # Callers edit a copy; _commit validates and saves it before use.
        return deepcopy(self._projects[project_id])

    def list_projects(self) -> list[Project]:
        return deepcopy(list(self._projects.values()))

    def _editable(self, project_id: str) -> Project:
        project = self.get_project(project_id)
        if project.archived_at is not None:
            raise ValueError("Reopen an archived project before editing it.")
        return project

    def _commit(self, project: Project, change=None, keep_undo=True) -> None:
        validate_project(project)
        projects = dict(self._projects)
        projects[project.id] = project
        undo = self._last_log_change if keep_undo else change
        self.repository.save({
            "schema_version": 1,
            "projects": [p.to_dict() for p in projects.values()],
            "last_log_change": undo,
        })
        # Update memory only after the save succeeds.
        self._projects = projects
        self._last_log_change = undo

    def create_project(self, title: str, deadline: date | None, planned_minutes: int,
                       daily_minutes: int, daily_limit_minutes: int | None = None,
                       start_date: date | None = None, color: str = "#7C83C4",
                       motivation: str = "", related_project_id: str | None = None,
                       catch_up_enabled: bool = True,
                       tasks: list[TaskNode] | None = None) -> Project:
        if tasks is not None and not isinstance(tasks, list):
            raise ValueError("Initial tasks must be a list of task nodes.")
        if related_project_id is not None:
            self.get_project(related_project_id)
        project = Project(
            title=title, start_date=start_date or self.today(), deadline=deadline,
            planned_minutes=planned_minutes, daily_minutes=daily_minutes,
            daily_limit_minutes=daily_minutes if daily_limit_minutes is None else daily_limit_minutes,
            color=color, motivation=motivation, related_project_id=related_project_id,
            catch_up_enabled=catch_up_enabled,
            tasks=deepcopy(tasks) if tasks is not None else [],
        )
        self._commit(project)  # Save the project and its initial tasks together.
        return self.get_project(project.id)

    def update_project(self, project_id: str, **changes) -> Project:
        allowed = {"title", "deadline", "daily_minutes", "daily_limit_minutes", "color",
                   "motivation", "note", "image_path", "outcome_completed", "related_project_id", "catch_up_enabled"}
        if not set(changes) <= allowed:
            raise ValueError("This field cannot be changed through update_project.")
        project = self._editable(project_id)
        related_id = changes.get("related_project_id")
        if related_id is not None:
            if not isinstance(related_id, str):
                raise ValueError("A related project must be a project ID or None.")
            if related_id == project_id:
                raise ValueError("A project cannot be related to itself.")
            self.get_project(related_id)
        for name, value in changes.items():
            setattr(project, name, value)
        self._commit(project)
        return self.get_project(project_id)

    def add_task(self, project_id: str, title: str, parent_id: str | None = None) -> TaskNode:
        project = self._editable(project_id)
        task = TaskNode(title)
        if parent_id is None:
            project.tasks.append(task)
        else:
            parent = project.find_task(parent_id)
            # New unfinished work reopens a completed leaf without losing its logs.
            parent.completed = False
            parent.children.append(task)
        self._commit(project)  # Includes the maximum-depth and cycle checks.
        return deepcopy(task)

    def rename_task(self, project_id: str, task_id: str, title: str) -> None:
        project = self._editable(project_id)
        project.find_task(task_id).title = title
        self._commit(project)

    def delete_task(self, project_id: str, task_id: str) -> None:
        """Remove a task and keep its work records at project level."""
        project = self._editable(project_id)
        task = project.find_task(task_id)
        removed_ids = set()

        def collect(node: TaskNode) -> None:
            removed_ids.add(node.id)
            for child in node.children:
                collect(child)

        def remove(nodes: list[TaskNode]) -> bool:
            for index, node in enumerate(nodes):
                if node.id == task_id:
                    nodes.pop(index)
                    return True
                if remove(node.children):
                    return True
            return False

        collect(task)
        remove(project.tasks)
        for log in project.logs:
            if log.task_id in removed_ids:
                log.task_id = None

        change = self._last_log_change
        # An undo cannot restore a reference to a deleted task.
        affects_undo = change is not None and change["project_id"] == project_id and any(
            snapshot is not None and snapshot.get("task_id") in removed_ids
            for snapshot in (change["before"], change["after"])
        )
        self._commit(project, keep_undo=not affects_undo)

    def set_task_completed(self, project_id: str, task_id: str, completed: bool) -> None:
        project = self._editable(project_id)
        task = project.find_task(task_id)
        if task.children:
            raise ValueError("A parent task is complete when all its subtasks are complete.")
        task.completed = completed
        self._commit(project)

    def _check_work_date(self, worked_on: date) -> None:
        if type(worked_on) is not date:
            raise ValueError("Choose a calendar date for the work record.")
        if worked_on > self.today():
            raise ValueError("Actual work cannot be recorded in the future.")

    def _work_minutes(self, minutes, intervals):
        """Derive minutes from periods, or retain a duration-only legacy record."""
        if intervals is None:
            if minutes is None:
                raise ValueError("Choose work periods or provide recorded minutes.")
            return minutes
        parsed = validate_work_intervals(intervals)
        local = local_timezone()
        today = self.today()
        now = datetime.now(timezone.utc) if today == date.today() else None
        for _, end, _ in parsed:
            if end.astimezone(local).date() > today or (now is not None and end > now):
                raise ValueError("Work periods cannot end in the future.")
        derived = work_interval_minutes(intervals)
        if minutes is not None and (type(minutes) is not int or minutes != derived):
            raise ValueError("Recorded minutes are calculated from the work periods.")
        return derived

    def add_work(self, project_id: str, worked_on: date, minutes: int | None = None,
                 task_id: str | None = None, note: str = "", *, source: str = "manual",
                 focus_details: dict | None = None,
                 work_intervals: list[dict] | None = None) -> WorkLog:
        project = self._editable(project_id)
        self._check_work_date(worked_on)
        minutes = self._work_minutes(minutes, work_intervals)
        log = WorkLog(worked_on, minutes, datetime.now(timezone.utc).isoformat(), task_id, note,
                      source=source, focus_details=deepcopy(focus_details),
                      work_intervals=deepcopy(work_intervals))
        project.logs.append(log)
        change = {"project_id": project_id, "before": None, "after": log.to_dict(),
                  "index": len(project.logs) - 1}
        self._commit(project, change, keep_undo=False)
        return deepcopy(log)

    def edit_work(self, project_id: str, log_id: str, worked_on: date,
                  minutes: int | None = None, note: str = "", *,
                  work_intervals=_UNCHANGED) -> None:
        project = self._editable(project_id)
        self._check_work_date(worked_on)
        index = self._log_index(project, log_id)
        before = project.logs[index].to_dict()
        log = project.logs[index]
        if work_intervals is _UNCHANGED:
            work_intervals = log.work_intervals
            if work_intervals is None and minutes is None:
                minutes = log.minutes
        minutes = self._work_minutes(minutes, work_intervals)
        log.worked_on, log.minutes, log.note = worked_on, minutes, note
        log.work_intervals = deepcopy(work_intervals)
        change = {"project_id": project_id, "before": before, "after": log.to_dict(), "index": index}
        self._commit(project, change, keep_undo=False)

    def delete_work(self, project_id: str, log_id: str) -> None:
        project = self._editable(project_id)
        index = self._log_index(project, log_id)
        before = project.logs.pop(index).to_dict()
        change = {"project_id": project_id, "before": before, "after": None, "index": index}
        self._commit(project, change, keep_undo=False)

    @staticmethod
    def _log_index(project: Project, log_id: str) -> int:
        for index, log in enumerate(project.logs):
            if log.id == log_id:
                return index
        raise ValueError("Work log not found.")

    def undo_last_work_change(self) -> None:
        """Restore the last work-record change and keep other project edits."""
        change = self._last_log_change
        if change is None:
            raise ValueError("No work-log change to undo.")
        project = self._editable(change["project_id"])
        before, after = change["before"], change["after"]
        if after is not None:
            index = self._log_index(project, after["id"])
            # Check the snapshot before replacing a record changed elsewhere.
            if project.logs[index].to_dict() != after:
                raise ValueError("The work log has changed; cannot safely undo it.")
            project.logs.pop(index)
        if before is not None:
            if any(log.id == before["id"] for log in project.logs):
                raise ValueError("Undo would duplicate a work log.")
            project.logs.insert(change["index"], WorkLog.from_dict(before))
        self._commit(project, keep_undo=False)

    def can_undo_work_change(self) -> bool:
        """Return whether a work-record change can be undone."""
        return self._last_log_change is not None

    def archive_project(self, project_id: str) -> None:
        project = self._editable(project_id)
        project.archived_at = datetime.now(timezone.utc).isoformat()
        preserve = self._last_log_change is None or self._last_log_change["project_id"] != project_id
        self._commit(project, keep_undo=preserve)

    def reopen_project(self, project_id: str) -> None:
        """Reopen an archived project with its existing records."""
        project = self.get_project(project_id)
        if project.archived_at is None:
            raise ValueError("Project is already active.")
        project.archived_at = None
        self._commit(project)

    def progress(self, project_id: str) -> dict:
        return time_bar(self.get_project(project_id))

    def focus_minutes_on(self, worked_on: date) -> int:
        """Sum confirmed focus-session minutes for a date, including archived work."""
        if type(worked_on) is not date:
            raise ValueError("The focus total requires an actual date.")
        tz = local_timezone()
        return sum(recorded_minutes_on(log, worked_on, tz) for project in self._projects.values()
                   for log in project.logs if log.source == "focus")

    def effort_for_task(self, project_id: str, task_id: str) -> int:
        project = self.get_project(project_id)
        return task_minutes(project, project.find_task(task_id))

    def schedule(self, project_id: str) -> dict:
        return suggest_schedule(self.get_project(project_id), self.today())
