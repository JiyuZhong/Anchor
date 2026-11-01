"""Daily focus and music totals from recorded activity intervals."""

from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .activity import interval_microseconds, parse_timestamp


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
    """Read either a model field or its saved dictionary entry."""
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
    stamp = parse_timestamp(value) if isinstance(value, str) else value
    if not isinstance(stamp, datetime) or stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Activity timestamps must include a time zone.")
    return stamp.astimezone(UTC)


def _day_start(on, tz):
    return datetime.combine(on, time.min, tzinfo=tz).astimezone(UTC)


def _clip(interval, start, end, *, confirmed=False):
    """Keep the part inside a day; only legacy observations need a scale."""
    left = _parse(interval["started_at"])
    right = _parse(interval["ended_at"])
    elapsed = (right - left).total_seconds()
    if elapsed <= 0:
        return None
    weight = 1.0 if confirmed else float(interval["seconds"]) / elapsed
    left, right = max(left, start), min(right, end)
    if right <= left or weight <= 0:
        return None
    return left, right, weight


def _hourly(interval, start, end, tz, bins, periods, metadata=None):
    confirmed = metadata is not None and metadata["timing_source"] == "confirmed"
    clipped = _clip(interval, start, end, confirmed=confirmed)
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
    """Split confirmed periods into local days without changing their total."""
    intervals = _get(log, "work_intervals")
    on = _get(log, "worked_on")
    on = date.fromisoformat(on) if isinstance(on, str) else on
    minutes = _get(log, "minutes", 0)
    if intervals is None:
        return {on: minutes}  # Older records keep their original work date.
    tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or local_timezone())
    by_day = {}
    for interval in intervals:
        cursor = _parse(interval["started_at"])
        end = _parse(interval["ended_at"])
        while cursor < end:
            on = cursor.astimezone(tz).date()
            following = min(end, _day_start(on + timedelta(days=1), tz))
            by_day[on] = by_day.get(on, 0) + interval_microseconds(cursor, following)
            cursor = following
    minute = 60_000_000
    result = {on: elapsed // minute for on, elapsed in by_day.items()}
    remaining = minutes - sum(result.values())
    # Give rounding minutes to the largest fractions; ties go to earlier days.
    ordered = sorted(by_day, key=lambda on: (-(by_day[on] % minute), on))
    for on in ordered[:remaining]:
        result[on] += 1
    return result


def recorded_minutes_on(log, on, tz=None):
    return recorded_minutes_by_day(log, tz).get(on, 0)


def _music_intersections(songs, work, start, end):
    """Walk two ordered lists without moving or extending any song."""
    result = []
    windows = None if work is None else [
        (_parse(span["started_at"]), _parse(span["ended_at"])) for span in work
    ]
    first_window = 0
    for song in songs:
        clipped = _clip(song, start, end)
        if clipped is None:
            continue
        left, right, weight = clipped
        if windows is None:
            result.append((song, left, right, weight))
            continue
        while first_window < len(windows) and windows[first_window][1] <= left:
            first_window += 1
        index = first_window
        while index < len(windows) and windows[index][0] < right:
            beginning = max(left, windows[index][0])
            ending = min(right, windows[index][1])
            if ending > beginning:
                result.append((song, beginning, ending, weight))
            index += 1
    return result


def _add_music_tracks(tracks, details, work, start, end, tz):
    """Add real listening intersections to the day's track totals."""
    total = 0.0
    for song, left, right, weight in _music_intersections(details.get("music", []), work, start, end):
        title = song.get("title", "").strip()
        if not title:
            continue
        key = (title, song.get("artist", ""), song.get("player", ""))
        track = tracks.setdefault(key, {"title": key[0], "artist": key[1], "player": key[2],
                                       "seconds": 0.0, "periods": []})
        seconds = (right - left).total_seconds() * weight
        track["seconds"] += seconds
        track["periods"].append({"started_at": left.astimezone(tz).isoformat(),
                                 "ended_at": right.astimezone(tz).isoformat(), "seconds": seconds})
        total += seconds
    return total


def summarize_day(projects_or_logs, selected_date, tz=None):
    """Group confirmed work periods or legacy observations by local date and hour."""
    if type(selected_date) is not date:
        raise ValueError("Choose a calendar date for statistics.")
    tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or local_timezone())
    start = _day_start(selected_date, tz)
    end = _day_start(selected_date + timedelta(days=1), tz)
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
        music_seconds += _add_music_tracks(tracks, details or {}, work, start, end, tz)
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
