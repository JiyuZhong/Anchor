"""Shared room coordinates and fixed camera definitions.
Coordinates are metres: x along the back wall, y towards it, z upwards."""
from dataclasses import dataclass
from math import sqrt
from types import MappingProxyType


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def unit(v):
    length = sqrt(dot(v, v))
    return tuple(x/length for x in v)


@dataclass(frozen=True)
class Camera:
    eye: tuple
    target: tuple
    scale: float
    anchor: tuple

    @property
    def basis(self):
        forward = unit(sub(self.target, self.eye))
        right = unit(cross(forward, (0, 0, 1)))
        return right, cross(right, forward), forward


CAMERAS = MappingProxyType({
    'room': Camera((11, -14, 10), (3.9, 2.9, 1.45), 102, (.63, .53)),
    'plan': Camera((2.6, 2.3, 3.0), (6.25, 5.35, 1.52), 218, (.73, .51)),
    'focus': Camera((6.5, -.5, 4.1), (2.65, 4.25, 1.25), 190, (.70, .54)),
    'collection': Camera((10.2, 1.4, 3.6), (6.05, 4.2, 1.35), 172, (.73, .53)),
    'music': Camera((5.8, -2.8, 3.1), (1.8, 1.65, .95), 245, (.73, .55)),
    'outside': Camera((2.65, 5.4, 2.0), (2.65, 12, 2.2), 130, (.50, .50)),
})

# Share landmark positions between drawing and hit tests.
LANDMARKS = MappingProxyType({
    'plan': (6.25, 5.07, 1.88),
    'focus': (2.6, 4.25, 1.16),
    'collection': (6.05, 2.18, .78),
    'music': (1.73, 1.34, 1.15),
    'outside': (2.8, 5.79, 2.0),
})
SHELF = (5.15, 5.06, 7.5, 5.72)
SHELF_BOARD_BASES = (.36, 1.07, 1.78, 2.61)
SHELF_BOARD_THICKNESS = .075
SHELF_LEVELS = tuple(height + SHELF_BOARD_THICKNESS for height in SHELF_BOARD_BASES[:3])


@dataclass(frozen=True)
class BookVolume:
    x: float
    y: float
    z: float
    width: float
    depth: float
    height: float

    @property
    def front(self):
        x, y, z = self.x, self.y, self.z
        return ((x, y, z+self.height), (x+self.width, y, z+self.height),
                (x+self.width, y, z), (x, y, z))

    @property
    def top(self):
        x, y, z = self.x, self.y, self.z+self.height
        return ((x, y, z), (x+self.width, y, z),
                (x+self.width, y+self.depth, z), (x, y+self.depth, z))

    def side(self, eye):
        x, y, z = self.x, self.y, self.z
        if eye[0] > x+self.width/2:
            x += self.width
            return ((x, y, z+self.height), (x, y+self.depth, z+self.height),
                    (x, y+self.depth, z), (x, y, z))
        return ((x, y+self.depth, z+self.height), (x, y, z+self.height),
                (x, y, z), (x, y+self.depth, z))


def book_volume(slot, facing, seed=0):
    """Place the book's bottom on its shelf board."""
    if type(slot) is not int or not 0 <= slot < 30 or facing not in ('spine', 'cover'):
        raise ValueError('Unknown book placement.')
    row, column = divmod(slot, 10)
    span = 3 if facing == 'cover' else 1
    if column + span > 10:
        raise ValueError('A front-facing cover needs three cells on one row.')
    thickness = .11+(seed % 3)*.008
    cover_width = .36+(seed % 3)*.012
    width, depth = (cover_width, thickness) if facing == 'cover' else (thickness, cover_width)
    x = 5.25 + column*.214 + (span*.214-width)/2
    return BookVolume(x, 5.12, SHELF_LEVELS[2-row], width, depth,
                      .48+(seed % 4)*.035)


WINDOW = ((.6, 5.79, 3.1), (4.65, 5.79, 3.1),
          (4.65, 5.79, 1.22), (.6, 5.79, 1.22))
