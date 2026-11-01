"""Daily focus and music totals from recorded activity intervals."""

from datetime import date, datetime, time, timedelta, timezone
from bisect import bisect_right
import math
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


def _hourly(interval, start, end, tz, bins, periods, metadata=None):
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
            if metadata:
                part.update(metadata)
            periods[hour].append(part)
            previous = (hour, local.utcoffset(), part)
        cursor = following
    return (right-left).total_seconds() * weight, (left, right)


def recorded_minutes_by_day(log, tz=None):
    """Split confirmed periods into local days while preserving recorded minutes."""
    intervals = _get(log, "work_intervals")
    on = _get(log, "worked_on")
    on = date.fromisoformat(on) if isinstance(on, str) else on
    minutes = _get(log, "minutes", 0)
    if intervals is None:
        return {on: minutes}
    tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or local_timezone())
    seconds_by_day = {}
    for interval in intervals:
        start, end = _parse(interval["started_at"]), _parse(interval["ended_at"])
        if end <= start:
            continue
        weight = float(interval["seconds"]) / (end-start).total_seconds()
        cursor = start
        while cursor < end:
            on = cursor.astimezone(tz).date()
            midnight = datetime.combine(on + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
            following = min(end, midnight)
            seconds_by_day[on] = seconds_by_day.get(on, 0.0) + (following-cursor).total_seconds() * weight
            cursor = following
    result = {on: math.floor(seconds / 60) for on, seconds in seconds_by_day.items()}
    remainder = minutes - sum(result.values())
    # Largest remainders keep one rounded minute from appearing on both dates.
    ordered = sorted(result, key=lambda on: (-(seconds_by_day[on] / 60 - result[on]), on))
    for on in ordered[:remainder]:
        result[on] += 1
    return result


def recorded_minutes_on(log, on, tz=None):
    return recorded_minutes_by_day(log, tz).get(on, 0)


def _music_parts(interval, start, end, windows, window_ends):
    clipped = _clip(interval, start, end)
    if clipped is None:
        return []
    left, right, weight = clipped
    if windows is None:
        return [(left, right, weight)]
    result = []
    index = bisect_right(window_ends, left)
    while index < len(windows) and windows[index][0] < right:
        begin, finish = max(left, windows[index][0]), min(right, windows[index][1])
        if finish > begin:
            result.append((begin, finish, weight))
        index += 1
    return result


def summarize_day(projects_or_logs, selected_date, tz=None):
    """Group confirmed work periods or legacy observations by local date and hour."""
    if type(selected_date) is not date:
        raise ValueError("Choose a calendar date for statistics.")
    tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or local_timezone())
    start = datetime.combine(selected_date, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(selected_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    # Repeated local hours share a column, which can exceed 60 minutes.
    bins = [0.0] * 24
    periods = [[] for _ in range(24)]
    recorded, manual, untimed, untimed_count, untimed_manual = 0, 0, 0, 0, 0
    measured, music_seconds = 0.0, 0.0
    timed, timed_focus, confirmed, manual_timed = 0.0, 0.0, 0.0, 0.0
    sessions, tracks = [], {}
    for log in _logs(projects_or_logs):
        source = _get(log, "source", "manual")
        details = _get(log, "focus_details")
        work = _get(log, "work_intervals")
        observed = (details or {}).get("segments", []) if source == "focus" else []
        intervals = work if work is not None else observed
        minutes = recorded_minutes_on(log, selected_date, tz)
        if minutes:
            if source == "focus":
                recorded += minutes
                if not intervals:
                    untimed += minutes
                    untimed_count += 1
            else:
                manual += minutes
                if not intervals:
                    untimed_manual += minutes
        if source == "focus" and details:
            for interval in details.get("segments", []):
                captured = _clip(interval, start, end)
                if captured is not None:
                    left, right, weight = captured
                    measured += (right-left).total_seconds() * weight
        metadata = {"log_id": _get(log, "id"), "source": source,
                    "timing_source": "confirmed" if work is not None else "observed"}
        for interval in intervals:
            seconds, bounds = _hourly(interval, start, end, tz, bins, periods, metadata)
            if bounds is None:
                continue
            timed += seconds
            if work is not None:
                confirmed += seconds
            if source == "focus":
                timed_focus += seconds
            else:
                manual_timed += seconds
            left, right = bounds
            sessions.append({**metadata, "started_at": left.astimezone(tz).isoformat(),
                             "ended_at": right.astimezone(tz).isoformat(), "seconds": seconds})
        windows = [(_parse(span["started_at"]), _parse(span["ended_at"])) for span in work] if work is not None else None
        window_ends = [finish for _, finish in windows] if windows is not None else []
        for interval in (details or {}).get("music", []):
            title = interval.get("title", "").strip()
            if not title:
                continue
            for left, right, weight in _music_parts(interval, start, end, windows, window_ends):
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
        "timed_work_seconds": timed, "timed_work_minutes": timed / 60,
        "timed_focus_seconds": timed_focus, "confirmed_work_seconds": confirmed,
        "manual_timed_seconds": manual_timed,
        "recorded_focus_minutes": recorded, "manual_minutes": manual,
        "untimed_focus_minutes": untimed, "untimed_focus_count": untimed_count,
        "untimed_manual_minutes": untimed_manual,
        "untimed_recorded_minutes": untimed + untimed_manual,
        "observed_music_seconds": music_seconds,
        "unobserved_music_seconds": max(0.0, timed-music_seconds),
        "sessions": sorted(sessions, key=lambda item: item["started_at"]),
        "tracks": sorted(tracks.values(), key=lambda item: (-item["seconds"], item["title"].casefold())),
        "has_timing": bool(sessions),
    }
