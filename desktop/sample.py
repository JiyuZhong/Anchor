"""Sample projects for disposable previews and demonstrations."""

from datetime import date, datetime, time, timedelta
from planner.statistics import local_timezone


def seed_sample(service):
    """Add examples to an empty preview repository."""
    if service.list_projects():
        return
    today = date.today()
    p = service.create_project(
        "COMP9001 project", today + timedelta(days=5), 480, 60, 90,
        start_date=today - timedelta(days=3), color="#D7B78D",
        motivation="Prepare a working demo and explain the code clearly.",
    )
    stage = service.add_task(p.id, "Prepare the demo")
    service.add_task(p.id, "Check the project files", stage.id)
    service.add_task(p.id, "Practise the presentation", stage.id)
    service.add_task(p.id, "Write the Padlet post")
    service.add_work(p.id, today - timedelta(days=2), 50, note="Checked saving and reopening projects.")
    service.add_work(p.id, today - timedelta(days=1), 40, note="Prepared the presentation outline.")
    # Fictional intervals keep the preview chart useful without reading a player.
    zone = local_timezone()
    at = lambda hour, minute: datetime.combine(today, time(hour, minute), tzinfo=zone).isoformat()
    details = {"version": 1, "measured_seconds": 1500.0,
        "segments": [
            {"started_at": at(9, 50), "ended_at": at(10, 10), "seconds": 1200.0},
            {"started_at": at(11, 30), "ended_at": at(11, 35), "seconds": 300.0}],
        "music": [
            {"started_at": at(9, 50), "ended_at": at(10, 2), "seconds": 720.0,
             "title": "Demo · Quiet morning", "artist": "Sample data", "player": "preview"},
            {"started_at": at(10, 2), "ended_at": at(10, 10), "seconds": 480.0,
             "title": "Demo · Paper lights", "artist": "Sample data", "player": "preview"},
            {"started_at": at(11, 30), "ended_at": at(11, 35), "seconds": 300.0,
             "title": "Demo · Paper lights", "artist": "Sample data", "player": "preview"}]}
    service.add_work(p.id, today, 25, note="Preview only: fictional focus and music observations.",
                     source="focus", focus_details=details)
    old = service.create_project(
        "Reading notes", today - timedelta(days=5), 300, 30,
        start_date=today - timedelta(days=16), color="#97B7AD",
        motivation="Keep notes from the chapters I read.",
    )
    service.add_work(old.id, today - timedelta(days=12), 80)
    service.add_work(old.id, today - timedelta(days=8), 65)
    service.update_project(old.id, note="Finished the first two chapters. Continue with chapter three next time.")
    service.archive_project(old.id)
