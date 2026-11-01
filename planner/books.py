"""Book appearance and placement on a three-row shelf."""

from copy import deepcopy
from pathlib import PurePosixPath
import re

# The current study uses "city"; keep other keys for older saved layouts.
LAYOUT_IDS = ("city", "attic", "garden")


TEMPLATES = {
    "linen": {"name": "Linen", "cover_color": "#8FA79D", "spine_color": "#6F8D85"},
    "classic": {"name": "Classic", "cover_color": "#74566A", "spine_color": "#604254"},
    "botanical": {"name": "Botanical", "cover_color": "#627C61", "spine_color": "#48644B"},
    "celestial": {"name": "Celestial", "cover_color": "#526482", "spine_color": "#394C6C"},
}


def _value(project, name, default=None):
    return project.get(name, default) if isinstance(project, dict) else getattr(project, name, default)


class BookService:
    def __init__(self, repository):
        self.repository = repository
        state = repository.load() if repository.path.exists() else {
            "schema_version": 1, "kind": "anchor_books", "appearances": {},
            "placements": {room_id: {} for room_id in LAYOUT_IDS},
        }
        self._validate(state)
        self._state = deepcopy(state)

    def snapshot(self):
        return deepcopy(self._state)

    @staticmethod
    def _project_id(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError("A book must belong to a project.")

    @staticmethod
    def _appearance(value):
        keys = {"template", "cover_color", "spine_color", "title", "cover_image", "spine_image"}
        if not isinstance(value, dict) or set(value) != keys:
            raise ValueError("Invalid book appearance.")
        if not isinstance(value["template"], str) or value["template"] not in TEMPLATES:
            raise ValueError("Choose one of the available book templates.")
        for key in ("cover_color", "spine_color"):
            if not isinstance(value[key], str) or re.fullmatch(r"#[0-9a-fA-F]{6}", value[key]) is None:
                raise ValueError("Book colours must use six-digit hex values, such as #8FA79D.")
        if not isinstance(value["title"], str) or len(value["title"]) > 200:
            raise ValueError("The book title must be at most 200 characters.")
        for key in ("cover_image", "spine_image"):
            path = value[key]
            if not isinstance(path, str):
                raise ValueError("Invalid book image path.")
            if path:
                parts = PurePosixPath(path).parts
                if len(parts) != 2 or parts[0] != "book-images" or parts[1] in (".", "..") or "\\" in path:
                    raise ValueError("Book images must be stored in the local book-images folder.")

    @staticmethod
    def _placement(value):
        if not isinstance(value, dict) or set(value) != {"slot", "facing"}:
            raise ValueError("Invalid book placement.")
        slot, facing = value["slot"], value["facing"]
        if facing not in ("spine", "cover"):
            raise ValueError("Choose spine or cover facing out.")
        if slot is None or slot == "auto":
            return
        if type(slot) is not int or not 0 <= slot < 30:
            raise ValueError("Choose one of the thirty shelf positions.")
        if facing == "cover" and slot % 10 > 7:
            raise ValueError("A cover needs three adjacent spaces in the same shelf row.")

    @classmethod
    def _validate(cls, state):
        try:
            if not isinstance(state, dict) or state.get("schema_version") != 1 or state.get("kind") != "anchor_books":
                raise ValueError("Unsupported book save format.")
            if not isinstance(state["appearances"], dict):
                raise ValueError("Invalid book appearance collection.")
            for pid, appearance in state["appearances"].items():
                cls._project_id(pid)
                cls._appearance(appearance)
            layouts = state["placements"]
            if not isinstance(layouts, dict) or set(layouts) != set(LAYOUT_IDS):
                raise ValueError("Invalid room book layouts.")
            for room in layouts.values():
                if not isinstance(room, dict):
                    raise ValueError("Invalid room book layout.")
                occupied = set()
                for pid, placement in room.items():
                    cls._project_id(pid)
                    cls._placement(placement)
                    if type(placement["slot"]) is int:
                        span = cls.cells(placement["slot"], placement["facing"])
                        if occupied.intersection(span):
                            raise ValueError("That position is reserved by another book. Choose an empty position or move the other book first.")
                        occupied.update(span)
        except (KeyError, TypeError) as exc:
            raise ValueError("Invalid book save. The original file has been preserved.") from exc

    @staticmethod
    def cells(slot, facing):
        return tuple(range(slot, slot + (3 if facing == "cover" else 1)))

    def appearance(self, project_id, default_color="#8FA79D"):
        self._project_id(project_id)
        if project_id in self._state["appearances"]:
            return deepcopy(self._state["appearances"][project_id])
        return {"template": "linen", "cover_color": default_color, "spine_color": default_color,
                "title": "", "cover_image": "", "spine_image": ""}

    def placement(self, project_id, room_id):
        if room_id not in LAYOUT_IDS:
            raise ValueError("Unknown room.")
        return deepcopy(self._state["placements"][room_id].get(project_id, {"slot": "auto", "facing": "spine"}))

    def layout(self, room_id, projects):
        """Fill available cells around the books with fixed positions."""
        if room_id not in LAYOUT_IDS:
            raise ValueError("Unknown room.")
        result, occupied = [], set()
        # Reserve fixed positions before placing automatic books.
        for project in projects:
            pid = _value(project, "id")
            placement = self.placement(pid, room_id)
            entry = {"id": pid, **placement, "appearance": self.appearance(pid, _value(project, "color", "#8FA79D"))}
            result.append(entry)
            if type(entry["slot"]) is int:
                occupied.update(self.cells(entry["slot"], entry["facing"]))
        for entry in result:
            if entry["slot"] != "auto":
                continue
            entry["slot"] = None
            # A front cover occupies three cells and cannot cross a shelf row.
            for slot in range(30):
                if entry["facing"] == "cover" and slot % 10 > 7:
                    continue
                cells = self.cells(slot, entry["facing"])
                if not occupied.intersection(cells):
                    entry["slot"] = slot
                    occupied.update(cells)
                    break
        return result

    def save_book(self, project_id, appearance, room_id, slot, facing, projects):
        self.save_books([{"id": project_id, "appearance": appearance, "room_id": room_id,
                          "slot": slot, "facing": facing}], projects)

    def save_books(self, changes, projects):
        """Save all edited books in one operation."""
        project_ids = {_value(project, "id") for project in projects}
        candidate = deepcopy(self._state)
        for change in changes:
            pid, room_id = change["id"], change["room_id"]
            if pid not in project_ids:
                raise ValueError("This project is no longer available.")
            if room_id not in LAYOUT_IDS:
                raise ValueError("Unknown room.")
            candidate["appearances"][pid] = deepcopy(change["appearance"])
            candidate["placements"][room_id][pid] = {"slot": change["slot"], "facing": change["facing"]}
        self._validate(candidate)
        self.repository.save(candidate)
        # Keep the previous state if validation or saving fails.
        self._state = candidate
