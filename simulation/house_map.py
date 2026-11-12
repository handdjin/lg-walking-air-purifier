"""앱과 시뮬레이터가 공유할 지도. 실제 배치는 house_map.json에만 정의한다."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    bounds: tuple  # x_min, y_min, x_max, y_max (양 끝 포함)
    target: tuple  # x, y

    def contains(self, position):
        x, y = position
        x1, y1, x2, y2 = self.bounds
        return x1 <= x <= x2 and y1 <= y <= y2


def coordinate(value):
    """잘못된 좌표를 지도 배열 접근 전에 거부한다."""
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(type(number) is not int for number in value)):
        raise ValueError("좌표는 정수 두 개 [x, y]여야 합니다.")
    return tuple(value)


class HouseMap:
    """직사각형 지도와 방 정보를 읽고 기본 설정 오류를 검사한다."""

    def __init__(self, data):
        grid = data["grid"]
        if (not grid or not all(isinstance(row, str) and row for row in grid)
                or len({len(row) for row in grid}) != 1):
            raise ValueError("지도는 길이가 같은 문자열 행으로 구성해야 합니다.")
        if any(tile not in "#.XD" for row in grid for tile in row):
            raise ValueError("지도에는 #, ., X, D만 사용할 수 있습니다.")
        self.grid = tuple(grid)
        self.width, self.height = len(grid[0]), len(grid)
        rooms = {}
        for item in data["rooms"]:
            room_id, name = item["id"], item["name"]
            bounds = item["bounds"]
            if not isinstance(room_id, str) or not room_id or room_id in rooms:
                raise ValueError("방 코드는 비어 있지 않은 고유한 문자열이어야 합니다.")
            if not isinstance(name, str) or not name:
                raise ValueError("방 이름은 비어 있지 않은 문자열이어야 합니다.")
            if (len(bounds) != 4 or any(type(n) is not int for n in bounds)
                    or not (0 <= bounds[0] <= bounds[2] < self.width)
                    or not (0 <= bounds[1] <= bounds[3] < self.height)):
                raise ValueError("방 영역은 지도 안의 [x_min, y_min, x_max, y_max]입니다.")
            room = Room(room_id, name, tuple(bounds), coordinate(item["target"]))
            if not room.contains(room.target) or not self.is_walkable(room.target):
                raise ValueError("방 도착 지점은 그 방 안의 이동 가능한 칸이어야 합니다.")
            rooms[room_id] = room
        self.rooms = MappingProxyType(rooms)
        for y, row in enumerate(self.grid):
            for x, tile in enumerate(row):
                owners = [room for room in rooms.values() if room.contains((x, y))]
                if len(owners) > 1:
                    raise ValueError("방 영역은 겹칠 수 없습니다.")
                if tile == "." and len(owners) != 1:
                    raise ValueError("모든 바닥 칸은 하나의 방에 속해야 합니다.")
                if tile == "D" and owners:
                    raise ValueError("문 칸은 방 경계 밖에 둡니다. 문의 현재 방은 None입니다.")
        self.start = coordinate(data["start"])
        if not self.is_walkable(self.start) or self.room_at(self.start) is None:
            raise ValueError("시작 위치는 방 안의 이동 가능한 칸이어야 합니다.")

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
        """문 위에서는 어느 방에도 속하지 않으므로 None을 반환한다."""
        if not self.is_walkable(position):
            return None
        for room in self.rooms.values():
            if room.contains(position):
                return room.id
        return None

    def to_dict(self):
        """JSON으로 보낼 수 있는 새 사본. 좌표는 모두 [x, y]이다."""
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
        }


def load_house_map(path=None):
    """실행 폴더에 관계없이 패키지 안의 기본 지도를 읽는다."""
    source = Path(path) if path is not None else Path(__file__).with_name("house_map.json")
    return HouseMap(json.loads(source.read_text(encoding="utf-8")))
