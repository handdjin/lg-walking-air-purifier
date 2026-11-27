"""Map shared by the app and simulator. The layout is defined in house_map.json."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    bounds: tuple  # x_min, y_min, x_max, y_max (inclusive)
    target: tuple  # x, y

    def contains(self, position):
        x, y = position
        x1, y1, x2, y2 = self.bounds
        return x1 <= x <= x2 and y1 <= y <= y2


def coordinate(value):
    """Validate coordinates before indexing the map."""
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(number) is not int for number in value)):
        raise ValueError("Coordinates must be two integers [x, y].")
    return tuple(value)


class HouseMap:
    """Load a rectangular grid and room definitions and validate the configuration."""

    def __init__(self, data):
        grid = data["grid"]
        if (not grid or not all(isinstance(row, str) and row for row in grid)
                or len({len(row) for row in grid}) != 1):
            raise ValueError("Map rows must be strings of equal length.")
        if any(tile not in "#.XD" for row in grid for tile in row):
            raise ValueError("Valid map symbols are #, ., X, and D.")
        self.grid = tuple(grid)
        self.width, self.height = len(grid[0]), len(grid)
        rooms = {}
        for item in data["rooms"]:
            room_id, name = item["id"], item["name"]
            bounds = item["bounds"]
            if not isinstance(room_id, str) or not room_id or room_id in rooms:
                raise ValueError("Room IDs must be unique, nonempty strings.")
            if not isinstance(name, str) or not name:
                raise ValueError("Room names must be nonempty strings.")
            if (len(bounds) != 4 or any(type(n) is not int for n in bounds)
                    or not (0 <= bounds[0] <= bounds[2] < self.width)
                    or not (0 <= bounds[1] <= bounds[3] < self.height)):
                raise ValueError("Room bounds must be [x_min, y_min, x_max, y_max] within the map.")
            room = Room(room_id, name, tuple(bounds), coordinate(item["target"]))
            if not room.contains(room.target) or not self.is_walkable(room.target):
                raise ValueError("Each room target must be a walkable cell inside that room.")
            rooms[room_id] = room
        self.rooms = MappingProxyType(rooms)
        for y, row in enumerate(self.grid):
            for x, tile in enumerate(row):
                owners = [room for room in rooms.values() if room.contains((x, y))]
                if len(owners) > 1:
                    raise ValueError("Room bounds cannot overlap.")
                if tile == "." and len(owners) != 1:
                    raise ValueError("Every floor cell must belong to one room.")
                if tile == "D" and owners:
                    raise ValueError("Doorways must be outside room bounds. Their current room is None.")
        self.start = coordinate(data["start"])
        if not self.is_walkable(self.start) or self.room_at(self.start) is None:
            raise ValueError("The start position must be a walkable cell inside a room.")
        # The charging dock defaults to the start position when the map omits it.
        self.dock = coordinate(data.get("dock", data["start"]))
        if not self.is_walkable(self.dock) or self.room_at(self.dock) is None:
            raise ValueError("The dock must be a walkable cell inside a room.")

    def is_walkable(self, position):
        x, y = coordinate(position)
        return (0 <= x < self.width and 0 <= y < self.height
                and self.grid[y][x] in ".D")

    def neighbors(self, position):
        x, y = position
        for candidate in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            if self.is_walkable(candidate):
                yield candidate

    def room_at(self, position):
        """Return None in a doorway, which belongs to no room."""
        if not self.is_walkable(position):
            return None
        for room in self.rooms.values():
            if room.contains(position):
                return room.id
        return None

    def to_dict(self):
        """JSON-serializable snapshot with [x, y] coordinates."""
        return {
            "width": self.width,
            "height": self.height,
            "grid": list(self.grid),
            "legend": {"#": "wall", ".": "floor", "X": "obstacle", "D": "door"},
            "rooms": [
                {"id": room.id, "name": room.name, "bounds": list(room.bounds),
                 "target": list(room.target)} for room in self.rooms.values()
            ],
            "start": list(self.start),
            "dock": list(self.dock),
        }


def load_house_map(path=None):
    """Load the packaged default map independently of the working directory."""
    source = Path(path) if path is not None else Path(__file__).with_name("house_map.json")
    return HouseMap(json.loads(source.read_text(encoding="utf-8")))
