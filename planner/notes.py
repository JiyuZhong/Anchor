"""Room note validation and random selection."""

import random


MAX_NOTES = 30
MAX_EDIT_LENGTH = 250
# Older notes can contain up to 1,000 characters.
MAX_SAVED_LENGTH = 1000


def validate_notes(notes, *, max_length=MAX_SAVED_LENGTH):
    """Validate saved notes and return a copy."""
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise ValueError(f"Keep at most {MAX_NOTES} room notes.")
    for note in notes:
        if not isinstance(note, str) or not note.strip():
            raise ValueError("Each room note must contain some text.")
        if len(note) > max_length:
            raise ValueError(f"Room notes must be at most {max_length} characters.")
    return list(notes)


def normalize_notes(settings):
    """Read current notes or the earlier single-note format."""
    if not isinstance(settings, dict):
        raise ValueError("Room settings must be an object.")
    if "notes" in settings:
        return validate_notes(settings["notes"])
    legacy = settings.get("note", "")
    if not isinstance(legacy, str):
        raise ValueError("The saved room note must be text.")
    return validate_notes([legacy]) if legacy.strip() else []


def select_next_note(notes, current=None, rng=None):
    """Choose another note when different text is available."""
    values = validate_notes(notes)
    if not values:
        return ""
    candidates = [value for value in values if value != current]
    chooser = rng if rng is not None else random.SystemRandom()
    return chooser.choice(candidates or values)
