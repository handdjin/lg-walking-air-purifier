"""데이터 생성기와 시뮬레이터가 함께 사용하는 1분 단위 공기질 환경.

모든 수치는 공기질규칙.md의 시뮬레이션 가정이다.
이 모듈은 이동, 관측 이력, 자동 정화 판단, AI 학습을 수행하지 않는다.
"""

from dataclasses import asdict, dataclass
import math
import random
from types import MappingProxyType

from .house_map import load_house_map


RULE_VERSION = "pm25-v1.1"
# 부분 분 정화 지원을 추가해도 기존 시드의 활동 시간표는 유지한다.
EVENT_SEED_VERSION = "pm25-v1"
MINUTES_PER_DAY = 1440
INITIAL_PM25 = 10.0
NATURAL_BASELINE = 10.0
NATURAL_DECAY_RATE = 0.01
PURIFICATION_RATE = 0.05
PURIFICATION_FLOOR = 5.0
# 방 코드와 이름은 지도 정의를 공통 기준으로 사용한다.
ROOM_NAMES = MappingProxyType({key: room.name for key, room in load_house_map().rooms.items()})
ACTIVITY_RATES = MappingProxyType({"cooking": 3.0, "cleaning": 2.0, "bedding": 2.0})


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name}은 {minimum} 이상의 정수여야 합니다.")


def _nonnegative_number(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name}은 유한한 0 이상의 수여야 합니다.")


def _room(room):
    if not isinstance(room, str) or room not in ROOM_NAMES:
        raise ValueError(f"올바르지 않은 방 코드: {room!r}")


def calculate_pm25(current_pm25, emission=0.0, purifying=False, *, purifying_seconds=60):
    """한 방의 1분 뒤 농도: 오염 증가 → 자연 감소 → 선택적 정화."""
    _nonnegative_number(current_pm25, "현재 농도")
    _nonnegative_number(emission, "오염 증가량")
    if type(purifying) is not bool:
        raise ValueError("purifying은 True 또는 False여야 합니다.")
    _nonnegative_number(purifying_seconds, "정화 시간")
    if purifying_seconds > 60:
        raise ValueError("1분 동안 정화한 시간은 60초 이하여야 합니다.")
    increased = current_pm25 + emission
    if not math.isfinite(increased):
        raise ValueError("농도와 오염 증가량의 합이 너무 큽니다.")
    after_natural = increased - max(increased - NATURAL_BASELINE, 0) * NATURAL_DECAY_RATE
    if purifying and purifying_seconds > 0:
        # 60초면 기존 5% 감소와 동일. 분 중간 도착/출발에는 실제 정화 시간만 반영.
        multiplier = (1 - PURIFICATION_RATE) ** (purifying_seconds / 60)
        return max(PURIFICATION_FLOOR, after_natural * multiplier)
    return after_natural


@dataclass(frozen=True)
class PollutionEvent:
    """활동 구간 [start_minute, end_minute). 시각은 하루 시작 후 경과 분."""

    room: str
    activity: str
    start_minute: int
    end_minute: int

    def __post_init__(self):
        _room(self.room)
        if not isinstance(self.activity, str) or self.activity not in ACTIVITY_RATES:
            raise ValueError("활동은 cooking, cleaning, bedding 중 하나여야 합니다.")
        _integer(self.start_minute, "시작 시각")
        _integer(self.end_minute, "종료 시각")
        if not self.start_minute < self.end_minute <= MINUTES_PER_DAY:
            raise ValueError("활동은 0~1440분 안에서 시작보다 늦게 종료해야 합니다.")

    def is_active(self, minute):
        return self.start_minute <= minute < self.end_minute


def generate_daily_events(seed=0, day_index=0, late_dinner=False):
    """독립 난수 생성기로 하루의 활동 4개를 만든다. 전역 random에 영향 없음."""
    _integer(seed, "seed")
    _integer(day_index, "day_index")
    if type(late_dinner) is not bool:
        raise ValueError("late_dinner는 True 또는 False여야 합니다.")
    rng = random.Random(f"{EVENT_SEED_VERSION}:{seed}:{day_index}")
    dinner_start = 20 * 60 if late_dinner else 18 * 60
    windows = (
        ("kitchen", "cooking", 7 * 60, 9 * 60, 10, 20),
        ("kitchen", "cooking", dinner_start, dinner_start + 120, 10, 20),
        ("living_room", "cleaning", 13 * 60, 17 * 60, 5, 10),
        ("bedroom", "bedding", 7 * 60, 10 * 60, 5, 10),
    )
    events = []
    for room, activity, earliest, latest, shortest, longest in windows:
        start = rng.randint(earliest, latest)  # 시작 범위 양 끝 포함
        duration = rng.randint(shortest, longest)
        events.append(PollutionEvent(room, activity, start, start + duration))
    return tuple(sorted(events, key=lambda event: (event.start_minute, event.room)))


class AirEnvironment:
    """하루짜리 환경. 모든 방은 00:00에 농도 10으로 시작한다.

    advance()는 정확히 1분 진행한다. 24:00 뒤 자동 초기화하지 않는다.
    새로운 독립 일별 시나리오는 새 인스턴스로 만든다.
    """

    def __init__(self, seed=0, day_index=0, late_dinner=False, events=None):
        _integer(seed, "seed")
        _integer(day_index, "day_index")
        if type(late_dinner) is not bool:
            raise ValueError("late_dinner는 True 또는 False여야 합니다.")
        generated = events is None
        schedule = (generate_daily_events(seed, day_index, late_dinner)
                    if generated else tuple(events))
        if not all(isinstance(event, PollutionEvent) for event in schedule):
            raise ValueError("events에는 PollutionEvent만 전달할 수 있습니다.")
        self._events = tuple(sorted(schedule, key=lambda event: (event.start_minute, event.room)))
        self._seed = seed
        self._day_index = day_index
        self._late_dinner = late_dinner
        self._generated = generated
        self._minute = 0
        self._pm25 = {room: INITIAL_PM25 for room in ROOM_NAMES}

    @property
    def minute(self):
        return self._minute

    def advance(self, purifying_room=None, *, purification_seconds=None):
        """현재 시각부터 다음 1분을 계산하고 갱신된 시각만 반환한다.

        purifying_room은 이번 1분 동안 정화할 방 하나 또는 None이다.
        이동 중에는 호출자가 None을 전달해야 한다. 정화 명령은 저장하지
        않으므로 다음 advance() 호출에도 필요한 경우 명시해야 한다.
        purification_seconds={방 코드: 정화 초}는 부분 분 정화용이다.
        한 청정기이므로 모든 방의 시간 합은 60초 이하여야 한다.
        purifying_room과 동시에 지정할 수 없다.
        """
        if purifying_room is not None:
            _room(purifying_room)
        exposure = {}
        if purification_seconds is not None:
            if purifying_room is not None or not isinstance(purification_seconds, dict):
                raise ValueError("정화 방 또는 방별 정화 시간 중 하나만 지정하세요.")
            exposure = dict(purification_seconds)
            for room, seconds in exposure.items():
                _room(room)
                _nonnegative_number(seconds, "정화 시간")
            if sum(exposure.values()) > 60:
                raise ValueError("한 청정기의 분당 총 정화 시간은 60초 이하여야 합니다.")
        elif purifying_room is not None:
            exposure[purifying_room] = 60
        if self._minute >= MINUTES_PER_DAY:
            raise ValueError("하루가 끝났습니다. 다음 독립 시나리오는 새 인스턴스로 시작하세요.")
        emissions = {room: 0.0 for room in ROOM_NAMES}
        for event in self._events:
            if event.is_active(self._minute):
                emissions[event.room] += ACTIVITY_RATES[event.activity]
        updated = {
            room: calculate_pm25(value, emissions[room], exposure.get(room, 0) > 0,
                                 purifying_seconds=exposure.get(room, 0))
            for room, value in self._pm25.items()
        }
        self._pm25 = updated
        self._minute += 1
        return self._minute

    def sample_current_room(self, current_room):
        """호출자가 전달한 현재 방 하나의 측정 결과를 반환한다.

        환경은 청정기 좌표를 모른다. 반드시 실제 이동 상태의 방 코드만
        전달해야 한다. 방문하지 않은 방을 자유롭게 조회하는 API로
        노출하면 안 된다. 문(None)에서는 측정할 수 없다.
        관측 이력 저장과 중복 측정 방지는 호출자가 담당한다.
        """
        _room(current_room)
        return {"minute": self._minute, "room": current_room,
                "pm25": self._pm25[current_room]}

    def get_ground_truth(self):
        """학습 정답·평가 전용. 미방문 방을 포함하므로 예측 입력에 사용 금지."""
        return {"minute": self._minute, "pm25": dict(self._pm25)}

    def get_scenario(self):
        """재현용 설정과 미래 사건 시간표. 에이전트·앱의 관측 API에 노출 금지."""
        return {
            "rule_version": RULE_VERSION,
            "event_seed_version": EVENT_SEED_VERSION,
            "partial_purification": "(1 - purification_rate) ** (seconds / 60)",
            "seed": self._seed,
            "day_index": self._day_index,
            "late_dinner": self._late_dinner,
            "schedule_source": "generated" if self._generated else "custom",
            "time_unit": "minute",
            "pm25_unit": "µg/m³",
            "initial_pm25": INITIAL_PM25,
            "natural_baseline": NATURAL_BASELINE,
            "natural_decay_rate": NATURAL_DECAY_RATE,
            "purification_rate": PURIFICATION_RATE,
            "purification_floor": PURIFICATION_FLOOR,
            "activity_rates": dict(ACTIVITY_RATES),
            "events": [asdict(event) for event in self._events],
        }
