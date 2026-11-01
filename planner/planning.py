"""Progress totals and daily time suggestions."""

from datetime import date, timedelta
from .models import Project, TaskNode
from .statistics import local_timezone, recorded_minutes_by_day


def time_bar(project: Project) -> dict:
    actual = sum(log.minutes for log in project.logs)
    return {
        "project_id": project.id,
        "planned_minutes": project.planned_minutes,
        "actual_minutes": actual,
        # Cap the bar's fill while retaining the full recorded total.
        "fill_ratio": min(actual / project.planned_minutes, 1.0),
        "outcome_completed": project.outcome_completed,
    }


def task_minutes(project: Project, task: TaskNode) -> int:
    """Sum this task's records and each child's records."""
    direct_minutes = {}
    for log in project.logs:
        direct_minutes[log.task_id] = direct_minutes.get(log.task_id, 0) + log.minutes

    def total(node):
        minutes = direct_minutes.get(node.id, 0)
        for child in node.children:
            minutes += total(child)
        return minutes

    return total(task)


def gentle_bonus_limit(project: Project) -> int:
    """Return the daily catch-up cap in whole minutes."""
    # Integer division rounds the 25% limit down.
    return min(15, project.daily_minutes // 4,
               max(project.daily_limit_minutes - project.daily_minutes, 0))


def _daily_totals(project: Project) -> dict:
    """Split each record once, then reuse its local-date totals."""
    totals = {}
    zone = local_timezone()
    for log in project.logs:
        for on, minutes in recorded_minutes_by_day(log, zone).items():
            totals[on] = totals.get(on, 0) + minutes
    return totals


def _ongoing_bonus(project: Project, today: date, daily_totals: dict) -> int:
    if not project.catch_up_enabled or today <= project.start_date:
        return 0
    yesterday_minutes = daily_totals.get(today - timedelta(days=1), 0)
    gap = max(project.daily_minutes - yesterday_minutes, 0)
    # Use yesterday's base-goal gap; +2 rounds division by three up.
    return min((gap + 2) // 3, gentle_bonus_limit(project))


def suggest_schedule(project: Project, from_date: date) -> dict:
    """Return remaining minutes for each suggested day."""
    return _build_schedule(project, from_date, _daily_totals(project))


def _build_schedule(project: Project, from_date: date, daily_totals: dict) -> dict:
    """Share the same totals between the schedule and its explanation."""
    if project.archived_at is not None:
        return {"days": [], "unscheduled_minutes": 0, "archived": True}
    start = max(from_date, project.start_date)
    days = []
    if project.deadline is None:
        for offset in range(7):
            on = start + timedelta(days=offset)
            already = daily_totals.get(on, 0)
            bonus = _ongoing_bonus(project, from_date, daily_totals) if on == from_date else 0
            target = min(project.daily_limit_minutes, project.daily_minutes + bonus)
            days.append({"date": on.isoformat(), "additional_minutes": max(target - already, 0)})
        return {"days": days, "unscheduled_minutes": 0, "archived": False}

    remaining = max(project.planned_minutes - sum(daily_totals.values()), 0)
    day_count = max((project.deadline - start).days + 1, 0)
    bonus_limit = gentle_bonus_limit(project) if project.catch_up_enabled else 0
    target_limit = min(project.daily_limit_minutes, project.daily_minutes + bonus_limit)
    for offset in range(day_count):
        on = start + timedelta(days=offset)
        already = daily_totals.get(on, 0)
        days_left = day_count - offset
        # Add today's work back before finding the daily total. Logging time
        # then reduces what remains, without raising the day's target.
        average_total = (remaining + already + days_left - 1) // days_left
        desired = project.daily_minutes
        if project.catch_up_enabled:
            desired = max(desired, average_total)
        target = min(target_limit, desired)
        additional = min(remaining, max(target - already, 0))
        days.append({"date": on.isoformat(), "additional_minutes": additional})
        remaining -= additional
    return {"days": days, "unscheduled_minutes": remaining, "archived": False}


def recovery_summary(project: Project, today: date) -> dict:
    """Summarise today's pace, extra time and remaining work for the interface."""
    daily_totals = _daily_totals(project)
    schedule = _build_schedule(project, today, daily_totals)
    ongoing = project.deadline is None
    baseline = project.daily_minutes
    yesterday = today - timedelta(days=1)
    elapsed_days = max((today - project.start_date).days, 0)
    if ongoing:
        yesterday_target = baseline if yesterday >= project.start_date else 0
        expected_before = yesterday_target
        recorded_before = daily_totals.get(yesterday, 0)
    else:
        total_days = max((project.deadline - project.start_date).days + 1, 0)
        elapsed_days = min(elapsed_days, total_days)
        expected_before = min(project.planned_minutes, elapsed_days * baseline)
        recorded_before = sum(minutes for on, minutes in daily_totals.items() if on < today)
        yesterday_target = 0
        if project.start_date <= yesterday <= project.deadline:
            earlier_days = (yesterday - project.start_date).days
            yesterday_target = min(baseline, max(project.planned_minutes - earlier_days * baseline, 0))
    unrecorded = max(expected_before - recorded_before, 0)
    yesterday_recorded = daily_totals.get(yesterday, 0)
    today_recorded = daily_totals.get(today, 0)
    # Use the schedule's target; the earlier totals explain how it changed.
    today_entry = next((day for day in schedule["days"] if day["date"] == today.isoformat()), None)
    additional = today_entry["additional_minutes"] if today_entry else 0
    target = today_recorded + additional
    usual_part = min(baseline, target)
    increase = max(target - baseline, 0) if additional else 0
    remaining = max(project.planned_minutes - sum(daily_totals.values()), 0)
    days_remaining = len(schedule["days"])
    spread_per_day = 0
    if ongoing:
        spread_per_day = _ongoing_bonus(project, today, daily_totals)
    elif days_remaining:
        spread_per_day = (unrecorded + days_remaining - 1) // days_remaining
    pressure = bool(schedule["unscheduled_minutes"])
    adjustment = bool(project.catch_up_enabled and additional and increase)
    if project.archived_at is not None:
        status = "archived"
    elif today < project.start_date:
        status = "upcoming"
    elif not ongoing and not remaining:
        status = "effort_covered"
    elif not ongoing and today > project.deadline:
        status = "overdue"
    elif today_entry is not None and not additional and today_recorded:
        status = "today_recorded"
    elif pressure:
        status = "capacity_pressure"
    elif adjustment:
        status = "gentle_adjustment"
    elif not project.catch_up_enabled:
        status = "catch_up_off"
    elif ongoing:
        status = "ongoing"
    else:
        status = "steady"
    return {
        "status": status,
        "date": today.isoformat(),
        "yesterday_date": yesterday.isoformat(),
        "baseline_minutes": baseline,
        "yesterday_target_minutes": yesterday_target,
        "yesterday_recorded_minutes": yesterday_recorded,
        "yesterday_gap_minutes": max(yesterday_target - yesterday_recorded, 0),
        "expected_before_today_minutes": expected_before,
        "recorded_before_today_minutes": recorded_before,
        "unrecorded_minutes": unrecorded,
        "days_remaining": days_remaining,
        "preview_days": 7 if ongoing else days_remaining,
        "ongoing": ongoing,
        "catch_up_enabled": project.catch_up_enabled,
        "catch_up_scope": "yesterday" if ongoing else "remaining_plan",
        "spread_per_day_minutes": spread_per_day,
        "today_recorded_minutes": today_recorded,
        "today_baseline_minutes": usual_part,
        "today_catch_up_minutes": increase,
        "today_target_minutes": target,
        "today_additional_minutes": additional,
        "gentle_increase_limit_minutes": gentle_bonus_limit(project),
        "has_adjustment": adjustment,
        "capacity_pressure": pressure,
        "daily_limit_minutes": project.daily_limit_minutes,
        "remaining_minutes": remaining,
        "unscheduled_minutes": schedule["unscheduled_minutes"],
    }
