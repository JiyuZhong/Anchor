"""Capture active focus intervals and the music observed during them."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
from time import monotonic


def _aware_datetime(value):
    if not isinstance(value, str):
        raise ValueError("Activity timestamps must be ISO text with a time zone.")
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise ValueError("Invalid activity timestamp.") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Activity timestamps need an explicit time zone.")
    return result


def _seconds(value):
    if type(value) not in (int, float):
        raise ValueError("Observed activity duration must be finite and non-negative.")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("Observed activity duration is too large.") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError("Observed activity duration must be finite and non-negative.")
    return number


def _after_seconds(start, seconds):
    """Add elapsed time in UTC so daylight-saving changes stay correct."""
    return (start.astimezone(timezone.utc) + timedelta(seconds=seconds)).astimezone(start.tzinfo)


def _validate_intervals(entries, *, music=False):
    if not isinstance(entries, list) or len(entries) > 10_000:
        raise ValueError("Invalid activity interval collection.")
    result = []
    previous_end = None
    expected = {"started_at", "ended_at", "seconds"}
    if music:
        expected |= {"title", "artist", "player"}
    for interval in entries:
        if not isinstance(interval, dict) or set(interval) != expected:
            raise ValueError("Invalid activity interval fields.")
        start = _aware_datetime(interval["started_at"])
        end = _aware_datetime(interval["ended_at"])
        seconds = _seconds(interval["seconds"])
        if end < start or (previous_end is not None and start < previous_end):
            raise ValueError("Activity intervals must be ordered without overlaps.")
        elapsed = (end.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds()
        if abs(elapsed - seconds) > .01:
            raise ValueError("An activity interval's timestamps and duration disagree.")
        if music:
            if any(not isinstance(interval[key], str) for key in ("title", "artist", "player")):
                raise ValueError("Music metadata must be text.")
            if not interval["title"].strip() or not interval["player"].strip():
                raise ValueError("A music interval needs its observed song and player.")
        result.append((start, end, seconds))
        previous_end = end
    return result


def validate_focus_details(details):
    """Check the stored focus-interval format."""
    if details is None:
        return
    if not isinstance(details, dict) or set(details) != {"version", "segments", "music", "measured_seconds"}:
        raise ValueError("Invalid focus activity details.")
    if type(details["version"]) is not int or details["version"] != 1:
        raise ValueError("Unsupported focus activity format.")
    segments = _validate_intervals(details["segments"])
    songs = _validate_intervals(details["music"], music=True)
    measured = _seconds(details["measured_seconds"])
    if abs(sum(seconds for _, _, seconds in segments) - measured) > .01:
        raise ValueError("Measured focus time must match its active segments.")
    segment_index = 0
    for start, end, _ in songs:
        # Scan the sorted lists once to check songs stay inside focus intervals.
        while segment_index < len(segments):
            segment_start, segment_end, _ = segments[segment_index]
            if segment_start <= start <= end <= segment_end:
                break
            if segment_end < end:
                segment_index += 1
            else:
                break
        if segment_index >= len(segments) or not (
                segments[segment_index][0] <= start <= end <= segments[segment_index][1]):
            raise ValueError("Music observations must lie inside an active focus segment.")


def validate_work_intervals(intervals):
    """Validate user-confirmed periods and return their parsed timestamps."""
    if not isinstance(intervals, list) or not intervals:
        raise ValueError("Add at least one work period.")
    parsed = _validate_intervals(intervals)
    if any(seconds <= 0 or end.astimezone(timezone.utc) <= start.astimezone(timezone.utc)
           for start, end, seconds in parsed):
        raise ValueError("Each work period must end after it starts.")
    return parsed


def work_interval_minutes(intervals):
    """Round the combined active periods up once to whole recorded minutes."""
    return math.ceil(sum(seconds for _, _, seconds in validate_work_intervals(intervals)) / 60)


class ActivityCapture:
    """Capture one focus session until it is saved or discarded."""

    def __init__(self, wall_clock=None, clock=monotonic):
        # Wall time locates intervals; the monotonic clock measures duration.
        self.wall_clock = wall_clock or (lambda: datetime.now().astimezone())
        self.clock = clock
        self.reset()

    def reset(self):
        self.state = "idle"
        self._segments = []
        self._music = []
        self._segment_start = None
        self._music_start = None
        self._song = None

    def _now(self):
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("The activity clock must return finite seconds.")
        return float(now)

    def _wall_now(self):
        value = self.wall_clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("The activity wall clock must include a time zone.")
        return value

    @staticmethod
    def _interval(start, now):
        wall, monotonic_start = start
        seconds = max(0.0, now - monotonic_start)
        return {"started_at": wall.isoformat(),
                "ended_at": _after_seconds(wall, seconds).isoformat(),
                "seconds": seconds}

    def _timeline_at(self, now):
        wall, monotonic_start = self._segment_start
        return _after_seconds(wall, max(0.0, now - monotonic_start))

    def _begin_segment(self):
        wall, now = self._wall_now(), self._now()
        # Clamp a backwards wall-clock change to the previous segment end.
        if self._segments:
            last_end = _aware_datetime(self._segments[-1]["ended_at"])
            wall = max(wall, last_end)
        self._segment_start = wall, now
        self.state = "running"
        if self._song:
            self._music_start = wall, now

    def start(self):
        if self.state != "idle":
            raise ValueError("Finish the current activity before starting another.")
        self._segments = []
        self._music = []
        self._begin_segment()

    def _close_music(self, now):
        if self._music_start is not None:
            interval = self._interval(self._music_start, now)
            interval["ended_at"] = self._timeline_at(now).isoformat()
            if interval["seconds"] > 0:
                self._music.append({**interval, **self._song})
        self._music_start = None

    def pause(self):
        if self.state != "running":
            raise ValueError("Only a running activity can be paused.")
        now = self._now()
        self._close_music(now)
        interval = self._interval(self._segment_start, now)
        if interval["seconds"] > 0:
            self._segments.append(interval)
        self._segment_start = None
        self.state = "paused"

    def resume(self):
        if self.state != "paused":
            raise ValueError("Only a paused activity can be resumed.")
        self._begin_segment()

    def observe_music(self, status, player=None):
        song = None
        if isinstance(status, dict) and status.get("state") == "playing":
            title = status.get("title")
            if isinstance(title, str) and title.strip():
                artist = status.get("artist", "")
                song = {"title": title.strip(),
                        "artist": artist.strip() if isinstance(artist, str) else "",
                        "player": player.strip() if isinstance(player, str) and player.strip() else "Music player"}
        # Repeated polls for the same track share one interval.
        if song == self._song:
            return
        if self.state == "running":
            now = self._now()
            self._close_music(now)
            self._song = song
            if song:
                self._music_start = self._timeline_at(now), now
        else:
            self._song = song

    def elapsed_seconds(self):
        seconds = sum(segment["seconds"] for segment in self._segments)
        if self.state == "running":
            seconds += self._interval(self._segment_start, self._now())["seconds"]
        return seconds

    def snapshot(self):
        """Copy intervals so a cancelled or failed save can be retried."""
        segments, music = deepcopy(self._segments), deepcopy(self._music)
        if self.state == "running":
            now = self._now()
            interval = self._interval(self._segment_start, now)
            if interval["seconds"] > 0:
                segments.append(interval)
            if self._music_start is not None:
                song_interval = self._interval(self._music_start, now)
                song_interval["ended_at"] = self._timeline_at(now).isoformat()
                if song_interval["seconds"] > 0:
                    music.append({**song_interval, **self._song})
        details = {"version": 1, "segments": segments, "music": music,
                   "measured_seconds": sum(segment["seconds"] for segment in segments)}
        validate_focus_details(details)
        return details
