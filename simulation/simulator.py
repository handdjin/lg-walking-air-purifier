"""방 이동 명령으로 경로를 만들고 step()마다 한 칸 이동한다."""

from collections import deque

from .house_map import load_house_map
from .pathfinding import find_path


class Simulator:
    """인스턴스마다 독립된 위치·목적지·남은 경로를 관리한다."""

    def __init__(self, house_map=None):
        self._map = house_map if house_map is not None else load_house_map()
        self._position = self._map.start
        self._destination = None
        self._path = deque()

    def get_map(self):
        """C의 앱에서 그릴 지도와 방 정보를 반환한다."""
        return self._map.to_dict()

    def get_state(self):
        """조회만 수행한다. 호출해도 청정기가 움직이지 않는다."""
        current_room = self._map.room_at(self._position)
        return {
            "current_room": current_room,
            "room_name": self._map.rooms[current_room].name if current_room else None,
            "position": list(self._position),
            "destination": self._destination,
            "status": "moving" if self._path else "idle",
            "remaining_path": [list(point) for point in self._path],
            "remaining_steps": len(self._path),
        }

    def move_to(self, room: str):
        """현재 칸부터 새 경로를 예약한다. 이 호출 자체로는 이동하지 않는다.

        이동 중 다시 호출하면 새 목적지로 경로를 교체한다.
        잘못된 방이나 도달 불가 요청은 기존 상태와 경로를 보존한다.
        """
        if not isinstance(room, str) or room not in self._map.rooms:
            raise ValueError(
                f"올바르지 않은 방 코드: {room!r}. "
                f"사용 가능한 코드: {', '.join(self._map.rooms)}"
            )
        path = find_path(self._map, self._position, self._map.rooms[room].target)
        # 경로 탐색이 성공한 뒤에만 기존 목적지와 경로를 교체한다.
        self._destination = room
        self._path = deque(path[1:])
        return self.get_state()

    def step(self):
        """남은 경로가 있으면 정확히 한 칸 이동하고 새 상태를 반환한다."""
        if self._path:
            self._position = self._path.popleft()
        return self.get_state()

    def render_map(self):
        """터미널용 문자 지도. R은 현재 청정기 위치이다."""
        rows = [list(row) for row in self._map.grid]
        x, y = self._position
        rows[y][x] = "R"
        return "\n".join("".join(row) for row in rows)
