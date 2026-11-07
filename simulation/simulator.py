"""첫 단계: 경로 탐색 없이 현재 방을 변경하는 최소 시뮬레이터."""

from types import MappingProxyType


# 방 코드는 팀 공통 설계와 동일하게 사용한다.
# 좌표와 문 연결 정보는 2D 지도 단계에서 팀과 합의한 뒤 추가한다.
ROOMS = MappingProxyType({
    "living_room": "거실",
    "kitchen": "주방",
    "bedroom": "침실",
})


class Simulator:
    """청정기 한 대의 현재 방을 저장한다. 새 인스턴스는 거실에서 시작한다."""

    def __init__(self) -> None:
        self._current_room = "living_room"

    def get_state(self) -> dict:
        """서버에서 JSON으로 변환할 수 있는 새 상태 사본을 반환한다."""
        return {
            "current_room": self._current_room,
            "room_name": ROOMS[self._current_room],
        }

    def move_to(self, room: str) -> dict:
        """방을 즉시 변경하고 상태를 반환한다. 잘못된 입력은 상태를 유지한다."""
        if not isinstance(room, str) or room not in ROOMS:
            raise ValueError(
                f"올바르지 않은 방 코드: {room!r}. "
                f"사용 가능한 코드: {', '.join(ROOMS)}"
            )

        self._current_room = room
        return self.get_state()
