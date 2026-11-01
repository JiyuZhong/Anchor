"""Legacy furniture layouts and rewards, unused by the current interface."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
import random
from types import MappingProxyType

from .storage import JsonRepository


@dataclass(frozen=True)
class Furniture:
    id: str
    name: str
    kind: str
    color: str
    style: str
    room_ids: tuple[str, ...] = ()  # Empty means usable in every room.
    description: str = ""

    def fits(self, room_id: str, slot: PlacementSlot) -> bool:
        return self.kind in slot.kinds and (not self.room_ids or room_id in self.room_ids)


@dataclass(frozen=True)
class Lamp(Furniture):
    light_color: str = "#FFE0A6"
    light_radius: float = .16
    intensity: float = .6


@dataclass(frozen=True)
class Plant(Furniture):
    leaf_color: str = "#6F9B7E"


@dataclass(frozen=True)
class Decoration(Furniture):
    pass


@dataclass(frozen=True)
class PlacementSlot:
    id: str
    name: str
    x: float
    y: float
    width: float
    height: float
    kinds: tuple[str, ...]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.width, self.height


@dataclass(frozen=True)
class RoomDefinition:
    id: str
    name: str
    description: str
    asset_name: str
    slots: tuple[PlacementSlot, ...]
    accent: str

    def slot(self, slot_id: str) -> PlacementSlot:
        for slot in self.slots:
            if slot.id == slot_id:
                return slot
        raise ValueError("This room has no such placement spot.")


def _slots(rectangles):
    """Fixed surfaces keep furniture aligned with the painted perspective."""
    definitions = (
        ("desk_left", "Desk · left", ("lamp", "plant", "decor")),
        ("desk_right", "Desk · right", ("lamp", "plant", "decor")),
        ("floor_left", "Floor · beside the desk", ("plant", "floor_decor")),
        ("floor_right", "Floor · beside the shelf", ("plant", "floor_decor")),
        ("wall_left", "Wall · above the desk", ("wall",)),
        ("floor_center", "Floor · centre", ("rug",)),
    )
    return tuple(PlacementSlot(key, name, *bounds, kinds)
                 for (key, name, kinds), bounds in zip(definitions, rectangles))


ROOMS = MappingProxyType({
    "city": RoomDefinition(
        "city", "City after dark", "A quiet room above the evening skyline.", "rooms/city.png",
        _slots(((.07, .48, .12, .20), (.23, .49, .10, .16),
                (.37, .62, .14, .25), (.67, .66, .14, .23),
                (.07, .18, .13, .17), (.39, .81, .29, .13))), "#D7B78D"),
    "attic": RoomDefinition(
        "attic", "Starlit attic", "A timber attic with space for small discoveries.", "rooms/attic.png",
        _slots(((.06, .47, .12, .21), (.23, .49, .10, .16),
                (.36, .63, .14, .24), (.66, .65, .14, .24),
                (.07, .20, .13, .17), (.40, .82, .28, .12))), "#B9AACF"),
    "garden": RoomDefinition(
        "garden", "Garden retreat", "A restful room beside a green, sheltered courtyard.", "rooms/garden.png",
        _slots(((.07, .49, .12, .19), (.24, .50, .10, .15),
                (.38, .63, .14, .25), (.67, .65, .14, .24),
                (.08, .19, .13, .17), (.39, .80, .29, .14))), "#9EBDAA"),
})


CATALOG = MappingProxyType({item.id: item for item in (
    Lamp("basic_lamp", "Amber desk lamp", "lamp", "#D7B78D", "desk_lamp",
         description="A warm light to begin with."),
    Decoration("linen_rug", "Linen rug", "rug", "#B8A28C", "rug",
               description="A soft foundation for any room."),
    Lamp("moon_lamp", "Little moon lamp", "lamp", "#D8DCE8", "moon_lamp",
         description="A gentle moon for your desk.", light_color="#DDE8FF", intensity=.45),
    Plant("jade_plant", "Jade plant", "plant", "#B48D72", "jade",
          description="A compact plant for a desk or quiet corner.", leaf_color="#7FA184"),
    Plant("trailing_plant", "Trailing pothos", "plant", "#C6B799", "trailing",
          description="A little greenery that spills over its pot.", leaf_color="#88A878"),
    Decoration("ceramic_vase", "Cloud ceramic vase", "decor", "#B2C4CF", "vase",
               description="A small handmade shape for the desk."),
    Decoration("star_mobile", "Paper star mobile", "wall", "#D3BD99", "mobile",
               description="A quiet constellation above your desk."),
    Lamp("city_orb", "City glass orb", "lamp", "#93B6D8", "orb", ("city",),
         "A city-room light inspired by the skyline.", light_color="#A1CDFF", intensity=.5),
    Decoration("attic_telescope", "Attic telescope", "floor_decor", "#A9A1BD", "telescope", ("attic",),
               "A little observatory, made for the attic."),
    Plant("garden_fern", "Courtyard fern", "plant", "#B8AA8F", "fern", ("garden",),
          "A broad-leaf fern at home in the garden retreat.", leaf_color="#729C78"),
)})


def _initial_state():
    return {
        "schema_version": 1,
        "kind": "anchor_home",
        "current_room": "city",
        "daily_goal": 25,
        "owned": {"basic_lamp": 1, "linen_rug": 1},
        "placements": {
            room_id: {
                "desk_left": {"furniture_id": "basic_lamp", "light_on": True},
                "floor_center": {"furniture_id": "linen_rug", "light_on": False},
            } for room_id in ROOMS
        },
        "days": {},
    }


class HomeService:
    """Legacy inventory, placement and daily reward operations."""

    def __init__(self, repository: JsonRepository, today=date.today, rng=None):
        self.repository, self.today = repository, today
        self.rng = rng if rng is not None else random.SystemRandom()
        state = repository.load() if repository.path.exists() else _initial_state()
        self._validate(state)
        self._state = deepcopy(state)

    @property
    def current_room(self) -> RoomDefinition:
        return ROOMS[self._state["current_room"]]

    @property
    def room(self) -> RoomDefinition:
        return self.current_room

    @property
    def catalog(self):
        return CATALOG

    @property
    def rooms(self):
        return ROOMS

    @property
    def inventory(self) -> dict:
        return deepcopy(self._state["owned"])

    @property
    def placements(self) -> dict:
        return deepcopy(self._state["placements"][self.current_room.id])

    def snapshot(self) -> dict:
        return deepcopy(self._state)

    @staticmethod
    def _goal(value):
        if type(value) is not int or not 1 <= value <= 1440:
            raise ValueError("The daily focus goal must be 1–1440 whole minutes.")

    @staticmethod
    def _focus_minutes(value):
        if type(value) is not int or value < 0:
            raise ValueError("Confirmed focus time must be a non-negative whole number.")

    @staticmethod
    def _furniture(furniture_id):
        if not isinstance(furniture_id, str) or furniture_id not in CATALOG:
            raise ValueError("Unknown furniture item.")
        return CATALOG[furniture_id]

    @classmethod
    def _validate(cls, state):
        """Check the room-save format and furniture references."""
        try:
            if not isinstance(state, dict) or state.get("schema_version") != 1 or state.get("kind") != "anchor_home":
                raise ValueError("Unsupported room save format.")
            if state["current_room"] not in ROOMS:
                raise ValueError("The saved room does not exist.")
            cls._goal(state["daily_goal"])
            owned = state["owned"]
            if not isinstance(owned, dict):
                raise ValueError("Invalid furniture inventory.")
            for furniture_id, quantity in owned.items():
                cls._furniture(furniture_id)
                if type(quantity) is not int or quantity <= 0:
                    raise ValueError("Furniture quantities must be positive whole numbers.")
            placements = state["placements"]
            if not isinstance(placements, dict) or set(placements) != set(ROOMS):
                raise ValueError("Invalid saved room layouts.")
            for room_id, arrangement in placements.items():
                if not isinstance(arrangement, dict):
                    raise ValueError("Invalid furniture placement.")
                used = Counter()
                for slot_id, instance in arrangement.items():
                    if not isinstance(instance, dict):
                        raise ValueError("Invalid placed furniture.")
                    slot = ROOMS[room_id].slot(slot_id)
                    item = cls._furniture(instance["furniture_id"])
                    if not item.fits(room_id, slot):
                        raise ValueError("Saved furniture is not compatible with its room or spot.")
                    if type(instance["light_on"]) is not bool:
                        raise ValueError("A lamp's on/off value must be boolean.")
                    if not isinstance(item, Lamp) and instance["light_on"]:
                        raise ValueError("Only lamps can emit light.")
                    used[item.id] += 1
                if any(count > owned.get(key, 0) for key, count in used.items()):
                    raise ValueError("A room places more copies than the inventory owns.")
            if not isinstance(state["days"], dict):
                raise ValueError("Invalid daily reward records.")
            for day, entry in state["days"].items():
                if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day:
                    raise ValueError("Invalid check-in date.")
                if not isinstance(entry, dict):
                    raise ValueError("Invalid daily check-in.")
                cls._goal(entry["goal"])
                reward_id = entry["reward_id"]
                if reward_id is None:
                    if entry["focus_minutes_at_claim"] is not None:
                        raise ValueError("Unclaimed days cannot have a claimed focus total.")
                else:
                    cls._furniture(reward_id)
                    cls._focus_minutes(entry["focus_minutes_at_claim"])
                    if entry["focus_minutes_at_claim"] < entry["goal"] or owned.get(reward_id, 0) < 1:
                        raise ValueError("Invalid claimed reward.")
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Room save is damaged; the original file has not been replaced.") from exc

    def _commit(self, candidate):
        self._validate(candidate)
        self.repository.save(candidate)
        self._state = candidate

    def select_room(self, room_id):
        if not isinstance(room_id, str) or room_id not in ROOMS:
            raise ValueError("Choose one of the available room layouts.")
        if room_id == self.current_room.id:
            return
        state = self.snapshot()
        state["current_room"] = room_id
        self._commit(state)

    def place(self, furniture_id, slot_id):
        item = self._furniture(furniture_id)
        slot = self.current_room.slot(slot_id)
        arrangement = self.placements
        if slot_id in arrangement:
            raise ValueError("This spot is occupied. Remove its furniture first.")
        if not item.fits(self.current_room.id, slot):
            raise ValueError("This furniture does not fit this room or placement spot.")
        used = sum(instance["furniture_id"] == item.id for instance in arrangement.values())
        if used >= self._state["owned"].get(item.id, 0):
            raise ValueError("There is no unused copy of this furniture in your inventory.")
        state = self.snapshot()
        state["placements"][self.current_room.id][slot_id] = {
            "furniture_id": item.id, "light_on": isinstance(item, Lamp),
        }
        self._commit(state)

    def remove(self, slot_id):
        self.current_room.slot(slot_id)
        if slot_id not in self.placements:
            raise ValueError("This placement spot is already empty.")
        state = self.snapshot()
        del state["placements"][self.current_room.id][slot_id]
        self._commit(state)

    def toggle_lamp(self, slot_id) -> bool:
        instance = self.placements.get(slot_id)
        if not instance or not isinstance(self._furniture(instance["furniture_id"]), Lamp):
            raise ValueError("There is no lamp in that spot.")
        state = self.snapshot()
        lamp = state["placements"][self.current_room.id][slot_id]
        lamp["light_on"] = not lamp["light_on"]
        self._commit(state)
        return lamp["light_on"]

    def set_daily_goal(self, minutes):
        self._goal(minutes)
        state = self.snapshot()
        state["daily_goal"] = minutes
        self._commit(state)

    def check_in(self):
        day = self.today().isoformat()
        if day in self._state["days"]:
            return  # Repeated clicks neither save again nor change today's goal.
        state = self.snapshot()
        state["days"][day] = {
            "goal": state["daily_goal"], "reward_id": None, "focus_minutes_at_claim": None,
        }
        self._commit(state)

    def reward_status(self, focus_minutes) -> dict:
        self._focus_minutes(focus_minutes)
        day = self.today().isoformat()
        entry = self._state["days"].get(day)
        goal = entry["goal"] if entry else self._state["daily_goal"]
        claimed = entry is not None and entry["reward_id"] is not None
        return {
            "date": day,
            "checked_in": entry is not None,
            "goal": goal,
            "next_goal": self._state["daily_goal"],
            "focus_minutes": focus_minutes,
            "remaining_minutes": max(goal - focus_minutes, 0),
            "eligible": entry is not None and not claimed and focus_minutes >= goal,
            "claimed": claimed,
            "reward_id": entry["reward_id"] if entry else None,
        }

    def draw(self, focus_minutes) -> Furniture:
        status = self.reward_status(focus_minutes)
        if not status["checked_in"]:
            raise ValueError("Check in today before claiming a furniture draw.")
        if status["claimed"]:
            raise ValueError("Today's furniture draw has already been claimed.")
        if not status["eligible"]:
            raise ValueError("Reach today's confirmed focus goal before drawing furniture.")
        # Draw from unowned items first, then allow duplicates once all are owned.
        candidates = [key for key in CATALOG if key not in self._state["owned"]]
        if not candidates:
            candidates = list(CATALOG)
        furniture_id = self.rng.choice(candidates)
        if furniture_id not in candidates:
            raise ValueError("The random selection returned an invalid furniture item.")
        state = self.snapshot()
        state["owned"][furniture_id] = state["owned"].get(furniture_id, 0) + 1
        entry = state["days"][status["date"]]
        entry["reward_id"] = furniture_id
        entry["focus_minutes_at_claim"] = focus_minutes
        self._commit(state)
        return CATALOG[furniture_id]
