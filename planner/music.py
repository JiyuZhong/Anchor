"""Allowed macOS player commands and playback-status parsing."""

from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class MusicApp:
    id: str
    name: str
    bundle_id: str
    paths: tuple[str, ...]


MUSIC_APPS = {
    "spotify": MusicApp("spotify", "Spotify", "com.spotify.client", (
        "/Applications/Spotify.app", "~/Applications/Spotify.app")),
    "music": MusicApp("music", "Apple Music", "com.apple.Music", (
        "/System/Applications/Music.app", "/Applications/Music.app")),
}


def app_path(app_id, platform=None):
    """Locate an installed player without starting it."""
    if app_id not in MUSIC_APPS:
        raise ValueError("Choose Spotify or Apple Music.")
    if (platform or sys.platform) != "darwin":
        return None
    return next((path for value in MUSIC_APPS[app_id].paths
                 if (path := Path(value).expanduser()).is_dir()), None)


def player_script(app_id, action="status", volume=None):
    """Build a supported player command."""
    if app_id not in MUSIC_APPS:
        raise ValueError("Choose Spotify or Apple Music.")
    commands = {"status": "", "playpause": "playpause", "next": "next track",
                "previous": "previous track"}
    if action == "volume":
        if type(volume) is not int or not 0 <= volume <= 100:
            raise ValueError("Music volume must be a whole number from 0 to 100.")
        command = f"set sound volume to {volume}"
    elif action in commands:
        command = commands[action]
    else:
        raise ValueError("Unknown music command.")
    bundle = MUSIC_APPS[app_id].bundle_id
    # Remove the field separator from track text before joining the reply.
    return f'''on cleanText(value)
    set oldDelimiters to AppleScript's text item delimiters
    set AppleScript's text item delimiters to character id 31
    set parts to text items of (value as text)
    set AppleScript's text item delimiters to " "
    set cleaned to parts as text
    set AppleScript's text item delimiters to oldDelimiters
    return cleaned
end cleanText
set separator to character id 31
if application id "{bundle}" is not running then
    return "not_running" & separator & separator & separator & "0"
end if
tell application id "{bundle}"
    {command}
    set playbackState to player state as text
    set trackTitle to ""
    set trackArtist to ""
    try
        set trackTitle to name of current track as text
        set trackArtist to artist of current track as text
    end try
    set playerVolume to sound volume as integer
end tell
return playbackState & separator & my cleanText(trackTitle) & separator & my cleanText(trackArtist) & separator & (playerVolume as text)
'''


def parse_player_status(output):
    """Decode the player's state, title, artist and volume."""
    fields = output.rstrip("\r\n").split(chr(31))
    if len(fields) != 4 or fields[0] not in (
            "playing", "paused", "stopped", "fast forwarding", "rewinding", "not_running"):
        raise ValueError("The music app returned an unreadable playback status. Try Connect again.")
    try:
        volume = int(fields[3])
    except ValueError as exc:
        raise ValueError("The music app returned an unreadable volume.") from exc
    if not 0 <= volume <= 100:
        raise ValueError("The music app returned an invalid volume.")
    return {"state": fields[0], "title": fields[1], "artist": fields[2], "volume": volume}


def music_error(stderr):
    """Turn common AppleScript errors into useful messages."""
    if "-1743" in stderr or "not authorized" in stderr.lower():
        return ("macOS has not allowed music control. Open System Settings → Privacy & Security → "
                "Automation and allow the app that launched Anchor (for example Terminal) to control "
                "your music app. Then try Connect again.")
    if "-600" in stderr or "isn't running" in stderr.lower():
        return "Your music app is not running. Open it, choose a playlist, then connect again."
    if "-10814" in stderr or "can't get application" in stderr.lower():
        return "The selected music app could not be found. Install it in Applications, then reopen this panel."
    if "-1712" in stderr:
        return "The music app did not respond. Check any macOS permission prompt, then try Connect again."
    return "The music app could not complete that action. Check that it is open and ready, then try Connect again."
