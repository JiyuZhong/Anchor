"""Daily focus and music totals from recorded activity intervals."""

from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc


def local_timezone():
    """Load the local time zone with its daylight-saving rules."""
    candidates = [os.environ.get("TZ", "").lstrip(":")]
    try:
        location = str(Path("/etc/localtime").resolve())
        if "/zoneinfo/" in location:
            candidates.append(location.split("/zoneinfo/", 1)[1])
    except OSError:
        pass
    for name in candidates:
        if name:
            try:
                return ZoneInfo(name)
            except (ZoneInfoNotFoundError, ValueError):
                pass
    try:
        with Path("/etc/localtime").open("rb") as local_file:
            return ZoneInfo.from_file(local_file, key="Local time")
    except (OSError, ValueError):
        pass
    return datetime.now().astimezone().tzinfo


def _get(value, name, default=None):
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def _logs(values):
    """Collect unique work logs from projects or individual records."""
    if _get(values, "logs") is not None or _get(values, "worked_on") is not None:
        values = [values]
    result, seen = [], set()
    for value in values:
        for log in _get(value, "logs", [value]):
            key = _get(log, "id") or id(log)
            if key not in seen:
                seen.add(key)
                result.append(log)
    return result


def _parse(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Activity timestamps must include a time zone.")
    return stamp.astimezone(UTC)


def _clip(interval, start, end):
    """Clip an interval to a day and return its duration scale."""
    left, right = _parse(interval["started_at"]), _parse(interval["ended_at"])
    wall_seconds = (right-left).total_seconds()
    seconds = float(interval["seconds"])
    if wall_seconds <= 0 or seconds <= 0:
        return None
    clipped_left, clipped_right = max(left, start), min(right, end)
    if clipped_right <= clipped_left:
        return None
    return clipped_left, clipped_right, seconds / wall_seconds


def _hourly(interval, start, end, tz, bins, periods):
    clipped = _clip(interval, start, end)
    if clipped is None:
        return 0.0, None
    left, right, weight = clipped
    cursor = left
    previous = None
    # UTC minutes handle skipped, repeated and half-hour daylight-saving changes.
    while cursor < right:
        boundary = cursor.replace(second=0, microsecond=0) + timedelta(minutes=1)
        following = min(right, boundary)
        local = cursor.astimezone(tz)
        hour = local.hour
        seconds = (following-cursor).total_seconds() * weight
        bins[hour] += seconds
        if previous is not None and previous[0] == hour and previous[1] == local.utcoffset():
            part = previous[2]
            part["ended_at"] = following.astimezone(tz).isoformat()
            part["seconds"] += seconds
        else:
            part = {"started_at": local.isoformat(), "ended_at": following.astimezone(tz).isoformat(), "seconds": seconds}
            periods[hour].append(part)
            previous = (hour, local.utcoffset(), part)
        cursor = following
    return (right-left).total_seconds() * weight, (left, right)


def summarize_day(projects_or_logs, selected_date, tz=None):
    """Group measured intervals by local date and hour."""
    if type(selected_date) is not date:
        raise ValueError("Choose a calendar date for statistics.")
    tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or local_timezone())
    start = datetime.combine(selected_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(selected_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    # Repeated local hours share a column, which can exceed 60 minutes.
    bins = [0.0] * 24
    periods = [[] for _ in range(24)]
    recorded, manual, untimed, untimed_count = 0, 0, 0, 0
    measured, music_seconds = 0.0, 0.0
    sessions, tracks = [], {}
    for log in _logs(projects_or_logs):
        on = _get(log, "worked_on")
        if isinstance(on, str):
            on = date.fromisoformat(on)
        source = _get(log, "source", "manual")
        details = _get(log, "focus_details")
        # Confirmed dates and minutes are separate from the observed timeline.
        if on == selected_date:
            minutes = _get(log, "minutes", 0)
            if source == "focus":
                recorded += minutes
                if not details or not details.get("segments"):
                    untimed += minutes
                    untimed_count += 1
            else:
                manual += minutes
        if source != "focus" or not details:
            continue
        for interval in details.get("segments", []):
            seconds, bounds = _hourly(interval, start, end, tz, bins, periods)
            if bounds is None:
                continue
            measured += seconds
            left, right = bounds
            sessions.append({"log_id": _get(log, "id"), "started_at": left.astimezone(tz).isoformat(),
                             "ended_at": right.astimezone(tz).isoformat(), "seconds": seconds})
        for interval in details.get("music", []):
            clipped = _clip(interval, start, end)
            title = interval.get("title", "").strip()
            if clipped is None or not title:
                continue
            left, right, weight = clipped
            seconds = (right-left).total_seconds() * weight
            key = (title, interval.get("artist", ""), interval.get("player", ""))
            track = tracks.setdefault(key, {"title": key[0], "artist": key[1], "player": key[2],
                                            "seconds": 0.0, "periods": []})
            track["seconds"] += seconds
            track["periods"].append({"started_at": left.astimezone(tz).isoformat(),
                                     "ended_at": right.astimezone(tz).isoformat(), "seconds": seconds})
            music_seconds += seconds
    return {
        "date": selected_date.isoformat(), "timezone": getattr(tz, "key", str(tz)),
        "hourly_seconds": bins, "hourly_minutes": [seconds / 60 for seconds in bins],
        "hourly_periods": [sorted(values, key=lambda item: _parse(item["started_at"])) for values in periods],
        "hours": [{"hour": hour, "seconds": seconds, "minutes": seconds/60}
                  for hour, seconds in enumerate(bins)],
        "measured_focus_seconds": measured, "measured_focus_minutes": measured / 60,
        "recorded_focus_minutes": recorded, "manual_minutes": manual,
        "untimed_focus_minutes": untimed, "untimed_focus_count": untimed_count,
        "observed_music_seconds": music_seconds,
        "unobserved_music_seconds": max(0.0, measured-music_seconds),
        "sessions": sorted(sessions, key=lambda item: item["started_at"]),
        "tracks": sorted(tracks.values(), key=lambda item: (-item["seconds"], item["title"].casefold())),
        "has_timing": bool(sessions),
    }
