"""Asynchronous Spotify and Apple Music controls for macOS."""

import sys
from collections import deque

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from planner.music import MUSIC_APPS, app_path, music_error, parse_player_status, player_script


class MusicController(QObject):
    snapshot_changed = Signal(object)
    failed = Signal(str)
    busy_changed = Signal(bool)
    opened = Signal()
    request_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.action = None
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.setInterval(30000)
        self.timeout.timeout.connect(self._timed_out)

    @property
    def busy(self):
        return self.process is not None

    def request(self, app_id, action="status", volume=None):
        if self.busy:
            return False
        if sys.platform != "darwin":
            self.failed.emit("Music-app control is available on macOS. You can still play music in your usual player.")
            return False
        try:
            path = app_path(app_id)
            if path is None:
                raise ValueError("This music app is not installed. Install it in Applications, then reopen this panel.")
            if action == "open":
                program, arguments = "/usr/bin/open", ["-a", str(path)]
            else:
                program, arguments = "/usr/bin/osascript", ["-e", player_script(app_id, action, volume)]
        except ValueError as exc:
            self.failed.emit(str(exc))
            return False
        process = QProcess(self)
        self.process, self.action = process, action
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._process_error)
        self.busy_changed.emit(True)
        self.timeout.start()
        process.start(program, arguments)
        return True

    def _take_process(self):
        process = self.process
        self.process = None
        self.timeout.stop()
        if process is not None:
            process.finished.disconnect(self._finished)
            process.errorOccurred.disconnect(self._process_error)
            process.deleteLater()
        self.busy_changed.emit(False)
        return process

    def _finished(self, exit_code, exit_status):
        if self.process is None:
            return
        process = self.process
        output = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
        action = self.action
        self._take_process()
        try:
            if exit_status != QProcess.ExitStatus.NormalExit or exit_code:
                self.failed.emit(music_error(error))
            elif action == "open":
                self.opened.emit()
            else:
                try:
                    self.snapshot_changed.emit(parse_player_status(output))
                except ValueError as exc:
                    self.failed.emit(str(exc))
        finally:
            self.request_finished.emit()

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._take_process()
            self.failed.emit("The Mac music controller could not start. Try opening your music app directly.")
            self.request_finished.emit()

    def _timed_out(self):
        self.cancel()
        self.failed.emit("The music app did not respond. Check any macOS permission prompt, then try Connect again.")
        self.request_finished.emit()

    def cancel(self):
        """Stop the helper without blocking widget destruction."""
        process = self.process
        self.process = None
        self.timeout.stop()
        if process is not None:
            process.finished.disconnect(self._finished)
            process.errorOccurred.disconnect(self._process_error)
            # Keep the stopped helper alive until its process has exited.
            process.setParent(QApplication.instance())
            if process.state() == QProcess.ProcessState.NotRunning:
                process.deleteLater()
            else:
                process.finished.connect(process.deleteLater)
                process.kill()
        self.busy_changed.emit(False)


class MusicSession(QObject):
    """Keep one player connection across page changes.
    Poll after Connect and queue commands while a request is running."""
    status_changed = Signal(object)
    playback_changed = Signal(bool)
    failed = Signal(str)
    busy_changed = Signal(bool)
    reset = Signal()
    opened = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.controller = MusicController(self)
        self.app_id = next((key for key in MUSIC_APPS if app_path(key) is not None), "spotify")
        self.connected = False
        self.last_status = None
        self.last_error = ""
        self._playing = False
        self._active_action = None
        self._active_interactive = False
        self._dispatching_status = False
        self._last_busy = False
        self._pending = deque()
        self._suspended = False
        self._closed = False
        self.poll = QTimer(self)
        self.poll.setInterval(2000)
        self.poll.timeout.connect(self.refresh)
        self.controller.snapshot_changed.connect(self._receive_status)
        self.controller.failed.connect(self._receive_error)
        self.controller.opened.connect(self.opened)
        self.controller.request_finished.connect(self._request_finished)

    @property
    def interactive_busy(self):
        return self._active_interactive or bool(self._pending)

    @property
    def volume_pending(self):
        return (self._active_action == "volume" and not self._dispatching_status) or any(action == "volume" for action, volume in self._pending)

    def _publish_busy(self):
        value = self.interactive_busy
        if value != self._last_busy:
            self._last_busy = value
            self.busy_changed.emit(value)

    def _publish_playback(self, playing):
        if self._playing != playing:
            self._playing = playing
            self.playback_changed.emit(playing)

    def select_app(self, app_id):
        if app_id not in MUSIC_APPS:
            raise ValueError("Choose Spotify or Apple Music.")
        if app_id == self.app_id:
            return
        self.poll.stop()
        self._pending.clear()
        self.controller.cancel()
        self._active_action = None
        self._active_interactive = False
        self.connected = False
        self.last_status = None
        self.last_error = ""
        self.app_id = app_id
        self._publish_playback(False)
        self._publish_busy()
        self.reset.emit()

    def connect_player(self):
        self.last_error = ""
        return self._enqueue("status")

    def open_player(self):
        return self._enqueue("open")

    def command(self, action, volume=None):
        if not self.connected:
            return False
        # Validate commands before adding them to the queue.
        player_script(self.app_id, action, volume)
        return self._enqueue(action, volume)

    def _enqueue(self, action, volume=None):
        if self._closed or self._suspended:
            return False
        if self.controller.busy:
            # Keep only the latest queued volume; preserve the order of other actions.
            if action == "volume" and self._pending and self._pending[-1][0] == "volume":
                self._pending[-1] = (action, volume)
            elif len(self._pending) < 32:
                self._pending.append((action, volume))
            else:
                return False
            self._publish_busy()
            return True
        return self._start(action, volume, interactive=True)

    def _start(self, action, volume=None, interactive=False):
        self._active_action = action
        self._active_interactive = interactive
        self._publish_busy()
        started = self.controller.request(self.app_id, action, volume)
        if not started:
            self._active_action = None
            self._active_interactive = False
            self._publish_busy()
        return started

    def refresh(self):
        if self.connected and not self._closed and not self._suspended and not self.controller.busy and not self._pending:
            self._start("status")

    def _receive_status(self, status):
        status = dict(status)
        changed = status != self.last_status
        self.connected = status["state"] != "not_running"
        self.last_status = status
        self.last_error = ""
        self._publish_playback(self.connected and status["state"] == "playing")
        if self.connected and not self._closed and not self._suspended:
            self.poll.start()
        else:
            self.poll.stop()
            self._pending.clear()
        # Refresh after a user command, even if the player returned unchanged data.
        if changed or self._active_interactive:
            self._dispatching_status = True
            try:
                self.status_changed.emit(dict(status))
            finally:
                self._dispatching_status = False

    def _receive_error(self, message):
        self.connected = False
        self.last_status = None
        self.last_error = message
        self.poll.stop()
        self._pending.clear()
        self._publish_playback(False)
        self.failed.emit(message)

    def _request_finished(self):
        self._active_action = None
        self._active_interactive = False
        if self._pending and not self._closed and not self._suspended:
            action, volume = self._pending.popleft()
            self._start(action, volume, interactive=True)
        self._publish_busy()

    def suspend(self):
        """Pause polling for standalone previews only."""
        self._suspended = True
        self.poll.stop()
        self._pending.clear()
        self.controller.cancel()
        self._active_action = None
        self._active_interactive = False
        self._publish_busy()

    def resume(self):
        if self._closed:
            return
        self._suspended = False
        if self.connected:
            self.poll.start()
            self.refresh()

    def shutdown(self):
        self._closed = True
        self.suspend()
        self.connected = False
        self._publish_playback(False)


def _label(text, role=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if role:
        widget.setObjectName(role)
    return widget


def _text(widget, value):
    if widget.text() != value:
        widget.setText(value)


def _enabled(widget, value):
    if widget.isEnabled() != value:
        widget.setEnabled(value)


def _button(text, action, role=None):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if role:
        widget.setObjectName(role)
    widget.clicked.connect(lambda checked=False: action())
    return widget


class MusicPanel(QWidget):
    def __init__(self, parent=None, session=None):
        super().__init__(parent)
        self._owns_session = session is None
        self.session = session if session is not None else MusicSession(self)
        self.controller = self.session.controller
        self.poll = self.session.poll
        self._available = {}
        self._volume_editing = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.addWidget(_label("PLAYER", "eyebrow"))
        self.app_combo = QComboBox()
        for app in MUSIC_APPS.values():
            installed = app_path(app.id) is not None
            self._available[app.id] = installed
            self.app_combo.addItem(app.name + ("" if installed else " · not installed"), app.id)
        self.app_combo.setCurrentIndex(self.app_combo.findData(self.session.app_id))
        layout.addWidget(self.app_combo)
        self.app_combo.currentIndexChanged.connect(self._select_app)
        top_row = QHBoxLayout()
        self.connect_button = _button("Connect", self.connect_player, "primary")
        self.open_button = _button("Open player ↗", self.open_player)
        top_row.addWidget(self.connect_button)
        top_row.addWidget(self.open_button)
        layout.addLayout(top_row)
        card = QFrame()
        card.setObjectName("subcard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 20, 18, 20)
        card_layout.setSpacing(8)
        self.state_label = _label("NOT CONNECTED", "eyebrow")
        self.title_label = _label("Nothing playing yet", "section")
        self.artist_label = _label("Choose a song in your player, then connect.", "muted")
        for child in (self.state_label, self.title_label, self.artist_label):
            card_layout.addWidget(child)
        layout.addWidget(card)
        transport = QHBoxLayout()
        self.previous_button = _button("Previous", lambda: self.command("previous"))
        self.play_button = _button("Play / pause", lambda: self.command("playpause"), "primary")
        self.next_button = _button("Next", lambda: self.command("next"))
        for child in (self.previous_button, self.play_button, self.next_button):
            transport.addWidget(child)
        layout.addLayout(transport)
        volume_row = QHBoxLayout()
        volume_row.addWidget(_label("Volume", "muted"))
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setAccessibleName("Music app volume")
        self.volume_slider.setValue(50)
        self.volume_slider.sliderReleased.connect(self._commit_volume)
        self.volume_slider.actionTriggered.connect(self._volume_key)
        volume_row.addWidget(self.volume_slider)
        self.volume_label = _label("—", "muted")
        self.volume_label.setMinimumWidth(34)
        self.volume_slider.valueChanged.connect(lambda value: _text(self.volume_label, str(value)))
        volume_row.addWidget(self.volume_label)
        layout.addLayout(volume_row)
        self.status_label = _label("Connect to read the current song and control playback.", "muted")
        layout.addWidget(self.status_label)
        layout.addWidget(_label("Music continues while you work or hide the interface.", "muted"))
        layout.addWidget(_label("macOS may ask for permission when you first connect.", "muted"))
        layout.addStretch()
        self.session.status_changed.connect(self._show_status)
        self.session.failed.connect(self._show_error)
        self.session.busy_changed.connect(self._update_buttons)
        self.session.reset.connect(self._reset)
        self.session.opened.connect(self._opened)
        if self.session.last_status is not None:
            self._show_status(self.session.last_status)
        elif self.session.last_error:
            self._show_error(self.session.last_error)
        if sys.platform != "darwin":
            _text(self.status_label, "Music-app control is available on macOS. You can still play music in your usual player.")
        self._update_buttons()

    @property
    def app_id(self):
        return self.session.app_id

    @property
    def connected(self):
        return self.session.connected

    @property
    def last_status(self):
        return self.session.last_status

    def _select_app(self, index):
        self.session.select_app(self.app_combo.itemData(index))

    def _reset(self):
        index = self.app_combo.findData(self.session.app_id)
        if self.app_combo.currentIndex() != index:
            self.app_combo.setCurrentIndex(index)
        _text(self.state_label, "NOT CONNECTED")
        _text(self.title_label, "Nothing playing yet")
        _text(self.artist_label, "Choose a song in your player, then connect.")
        _text(self.status_label, "Connect to read the current song and control playback.")
        _text(self.volume_label, "—")
        _text(self.play_button, "Play / pause")
        self._update_buttons()

    def _update_buttons(self, busy=False):
        available = sys.platform == "darwin" and self._available.get(self.app_id, False)
        idle = not self.session.interactive_busy
        _enabled(self.app_combo, idle)
        _enabled(self.connect_button, available and idle)
        _text(self.connect_button, "Refresh" if self.connected else "Connect")
        _enabled(self.open_button, available and idle)
        # The session queues commands, so background reads need not disable controls.
        for child in (self.previous_button, self.play_button, self.next_button, self.volume_slider):
            _enabled(child, available and self.connected)

    def connect_player(self):
        if not self.connected:
            _text(self.status_label, "Connecting… Check for a macOS permission prompt.")
        self.session.connect_player()

    def refresh(self):
        self.session.refresh()

    def open_player(self):
        self.session.open_player()

    def _opened(self):
        _text(self.status_label, "Choose a playlist in your music app, then press Connect here.")

    def command(self, action, volume=None):
        if self.connected and self.isVisible():
            self.session.command(action, volume)

    def _volume_key(self, action):
        if not self.volume_slider.isSliderDown():
            # Wait one event before reading the slider value changed by Qt.
            self._volume_editing = True
            QTimer.singleShot(0, self, self._commit_volume)

    def _commit_volume(self):
        self.command("volume", self.volume_slider.value())
        self._volume_editing = False

    def _show_status(self, status):
        if status["state"] == "not_running":
            _text(self.state_label, "PLAYER CLOSED")
            _text(self.title_label, "Open your music app")
            _text(self.artist_label, "Choose a playlist, then connect again.")
            _text(self.status_label, "Connecting does not open an app or start music automatically.")
        else:
            _text(self.state_label, status["state"].upper())
            _text(self.title_label, status["title"] or "Choose a song in your music app")
            _text(self.artist_label, status["artist"] or MUSIC_APPS[self.app_id].name)
            _text(self.play_button, "Pause  Ⅱ" if status["state"] == "playing" else "Play  ▷")
            if not self._volume_editing and not self.volume_slider.isSliderDown() and not self.session.volume_pending:
                if self.volume_slider.value() != status["volume"]:
                    self.volume_slider.setValue(status["volume"])
                _text(self.volume_label, str(status["volume"]))
            _text(self.status_label, "Connected to " + MUSIC_APPS[self.app_id].name + ". Choose playlists in that app.")
        self._update_buttons()

    def _show_error(self, message):
        _text(self.state_label, "CONNECTION PAUSED")
        _text(self.status_label, message)
        self._update_buttons()

    def hideEvent(self, event):
        if self._owns_session:
            self.session.suspend()
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if self._owns_session:
            self.session.resume()


def build_music(window):
    content = window.make_panel("Listening room", "Music from your desktop player.")
    window.music_panel = MusicPanel(window.panel, session=window.music_session)
    content.addWidget(window.music_panel)
