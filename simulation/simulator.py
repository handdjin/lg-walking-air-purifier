"""이동·가상 시간·관측·정화를 하나의 순서로 진행하는 시뮬레이터."""

from collections import deque
from copy import deepcopy

from .environment import AirEnvironment, MINUTES_PER_DAY, ROOM_NAMES
from .house_map import load_house_map
from .pathfinding import find_path


TICK_SECONDS = 10
MEASUREMENT_INTERVAL_SECONDS = 10 * 60
PURIFY_ON = 35
PURIFY_OFF = 15


class Simulator:
    """처음에는 일시정지 상태. start() 후 step()마다 가상 시간이 진행된다.

    외부 서버가 step() 호출 주기를 관리한다. 자체 스레드나 실시간 타이머는 없다.
    """

    def __init__(self, house_map=None, *, seed=0, day_index=0,
                 late_dinner=False, events=None, tick_seconds=TICK_SECONDS):
        self._map = house_map if house_map is not None else load_house_map()
        if set(self._map.rooms) != set(ROOM_NAMES):
            raise ValueError("지도와 공기질 환경의 방 코드가 일치해야 합니다.")
        if type(tick_seconds) is not int or tick_seconds <= 0 or 60 % tick_seconds:
            raise ValueError("tick_seconds는 60의 양의 정수 약수여야 합니다.")
        self._tick_seconds = tick_seconds
        self._environment_options = {
            "seed": seed, "day_index": day_index, "late_dinner": late_dinner,
            "events": None if events is None else tuple(events),
        }
        self.reset()

    def reset(self):
        """기존 위치·목적지·경로 초기화를 유지하고 시간·환경·관측도 초기화한다."""
        environment = AirEnvironment(**self._environment_options)
        self._position = self._map.start
        self._destination = None
        self._path = deque()
        self._environment = environment
        self._seconds = 0
        self._running = False
        self._purifying = False
        self._exposure = {}  # 이번 1분 중 방별로 실제 정화한 가상 초
        self._observations = {room: None for room in self._map.rooms}
        self._history = []
        self._record("reset")
        self._measure_current_room("initial")
        return self.get_state()

    def start(self):
        """이동·대기·정화 상태를 유지하며 가상 시간 진행을 허용한다."""
        if self._seconds >= MINUTES_PER_DAY * 60:
            raise ValueError("하루가 종료되었습니다. reset() 후 시작하세요.")
        if not self._running:
            self._running = True
            self._record("start")
        return self.get_state()

    def pause(self):
        """위치·경로·정화 설정을 보존하고 가상 시간 진행을 멈춘다."""
        if self._running:
            self._running = False
            self._record("pause")
        return self.get_state()

    def _record(self, event_type, **details):
        self._history.append({"time_seconds": self._seconds, "type": event_type, **details})

    def _set_purifying(self, enabled, reason):
        if self._purifying != enabled:
            self._purifying = enabled
            self._record("purification_on" if enabled else "purification_off",
                         room=self._map.room_at(self._position), reason=reason)

    def _measure_current_room(self, reason):
        """목적지 도착 또는 정지 중에만 호출. 방 코드는 실제 좌표에서 얻는다."""
        room = self._map.room_at(self._position)
        if room is None or self._path:
            return
        previous = self._observations[room]
        if previous and previous["measured_at_seconds"] == self._seconds:
            return  # 같은 방·시각의 도착 및 정기 측정 중복 방지
        sample = self._environment.sample_current_room(room)
        observation = {
            "pm25": sample["pm25"],
            "measured_at_seconds": self._seconds,
            "source_minute": sample["minute"],
        }
        self._observations[room] = observation
        self._record("measurement", room=room, reason=reason, **observation)
        if sample["pm25"] >= PURIFY_ON:
            self._set_purifying(True, "measurement")
        elif sample["pm25"] <= PURIFY_OFF:
            self._set_purifying(False, "measurement")

    def get_map(self):
        return self._map.to_dict()

    def get_state(self):
        """앱·정책용 상태. 미관측 방의 실제 농도와 미래 사건은 포함하지 않는다."""
        room = self._map.room_at(self._position)
        observations = {}
        for room_id, observation in self._observations.items():
            observations[room_id] = (
                {**observation, "age_seconds": self._seconds - observation["measured_at_seconds"]}
                if observation else
                {"pm25": None, "measured_at_seconds": None, "source_minute": None,
                 "age_seconds": None}
            )
        return {
            "current_room": room,
            "room_name": self._map.rooms[room].name if room else None,
            "position": list(self._position),
            "destination": self._destination,
            "status": "moving" if self._path else ("purifying" if self._purifying else "idle"),
            "remaining_path": [list(point) for point in self._path],
            "remaining_steps": len(self._path),
            "simulation_time_seconds": self._seconds,
            "environment_minute": self._environment.minute,
            "tick_seconds": self._tick_seconds,
            "is_running": self._running,
            "is_purifying": self._running and self._purifying and not self._path,
            "finished": self._seconds >= MINUTES_PER_DAY * 60,
            "observations": observations,
        }

    def move_to(self, room: str):
        """경로를 예약한다. 도달 불가·잘못된 요청은 현재 상태를 보존한다."""
        if not isinstance(room, str) or room not in self._map.rooms:
            raise ValueError(f"올바르지 않은 방 코드: {room!r}")
        if self._seconds >= MINUTES_PER_DAY * 60:
            raise ValueError("하루가 종료되었습니다. reset() 후 이동하세요.")
        path = find_path(self._map, self._position, self._map.rooms[room].target)
        # 경로 탐색 성공 전에는 기존 이동·정화 상태를 변경하지 않는다.
        if path[1:]:
            self._set_purifying(False, "move_requested")
        self._destination = room
        self._path = deque(path[1:])
        self._record("move_requested", destination=room)
        if not self._path:
            self._measure_current_room("arrival")
        return self.get_state()

    def step(self):
        """실행 중일 때만 한 tick 진행한다. 도착 후에도 환경 시간은 계속 흐른다.

        순서: 지난 구간 정화 시간 집계 → 분 경계의 환경 갱신 → 한 칸 이동
        → 시각 갱신 → 도착/정기 측정 → 정화 판단. 도착 직전 이동 구간은
        새 방의 정화 시간으로 계산하지 않는다.
        """
        if not self._running:
            return self.get_state()
        next_seconds = self._seconds + self._tick_seconds
        moving = bool(self._path)
        exposure = dict(self._exposure)
        room = self._map.room_at(self._position)
        if not moving and self._purifying and room is not None:
            exposure[room] = exposure.get(room, 0) + self._tick_seconds
        if next_seconds % 60 == 0:
            self._environment.advance(purification_seconds=exposure)
            exposure = {}
        self._exposure = exposure
        if moving:
            self._position = self._path.popleft()
        self._seconds = next_seconds
        if moving and not self._path:
            self._record("arrival", room=self._map.room_at(self._position))
            self._measure_current_room("arrival")
        elif not self._path and room is not None:
            observation = self._observations[room]
            if observation is None or self._seconds - observation["measured_at_seconds"] >= MEASUREMENT_INTERVAL_SECONDS:
                self._measure_current_room("periodic")
        if self._seconds == MINUTES_PER_DAY * 60:
            self._running = False
            self._set_purifying(False, "day_finished")
            self._record("day_finished")
        return self.get_state()

    def get_history(self):
        """실제로 발생한 명령·측정 이력의 사본을 반환한다."""
        return deepcopy(self._history)

    def get_ground_truth(self):
        """학습 정답·평가 전용. 일반 앱 상태 API에는 전달하지 않는다."""
        return self._environment.get_ground_truth()

    def get_scenario(self):
        """재현용 환경 설정. 미래 사건이 포함되어 앱·예측 입력으로 사용 금지."""
        return {**self._environment.get_scenario(), "tick_seconds": self._tick_seconds,
                "measurement_interval_seconds": MEASUREMENT_INTERVAL_SECONDS,
                "purify_on": PURIFY_ON, "purify_off": PURIFY_OFF}

    def render_map(self):
        rows = [list(row) for row in self._map.grid]
        x, y = self._position
        rows[y][x] = "R"
        return "\n".join("".join(row) for row in rows)
