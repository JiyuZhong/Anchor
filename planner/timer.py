"""Track elapsed focus time across starts, pauses and resumes."""

from time import monotonic


class FocusTimer:
    def __init__(self, clock=monotonic):
        self._clock = clock
        self._started_at = None
        self._accumulated = 0.0
        self.state = "idle"

    def start(self) -> None:
        if self.state != "idle":
            raise ValueError("Finish the current session before starting another.")
        self._accumulated = 0.0
        self._started_at = self._clock()
        self.state = "running"

    def elapsed_seconds(self) -> float:
        if self.state == "running":
            return self._accumulated + self._clock() - self._started_at
        return self._accumulated

    def pause(self) -> None:
        if self.state != "running":
            raise ValueError("Only a running session can be paused.")
        # Keep active seconds and stop reading the clock until resumed.
        self._accumulated = self.elapsed_seconds()
        self._started_at = None
        self.state = "paused"

    def resume(self) -> None:
        if self.state != "paused":
            raise ValueError("Only a paused session can be resumed.")
        self._started_at = self._clock()
        self.state = "running"

    def finish(self) -> float:
        if self.state == "idle":
            raise ValueError("There is no active session.")
        result = self.elapsed_seconds()
        self._started_at = None
        self._accumulated = 0.0
        self.state = "idle"
        # The window resets only after saving or explicitly discarding a session.
        return result
