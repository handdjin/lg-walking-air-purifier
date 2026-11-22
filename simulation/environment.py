"""One-minute air quality environment shared by the data generator and simulator.

The values implement the project's simulated air quality rules.
Movement, observation history, automatic purification decisions, and AI training are handled separately.
"""

from dataclasses import asdict, dataclass
import math
import random
from types import MappingProxyType

from .house_map import load_house_map


RULE_VERSION = "pm25-v1.1"
# Preserve seeded activity schedules when accounting for partial minutes of purification.
EVENT_SEED_VERSION = "pm25-v1"
MINUTES_PER_DAY = 1440
INITIAL_PM25 = 10.0
NATURAL_BASELINE = 10.0
NATURAL_DECAY_RATE = 0.01
PURIFICATION_RATE = 0.05
PURIFICATION_FLOOR = 5.0
# Use the map as the common source for room IDs and display names.
ROOM_NAMES = MappingProxyType({key: room.name for key, room in load_house_map().rooms.items()})
ACTIVITY_RATES = MappingProxyType({"cooking": 3.0, "cleaning": 2.0, "bedding": 2.0})


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer greater than or equal to {minimum}.")


def _nonnegative_number(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be a finite, nonnegative number.")


def _room(room):
    if not isinstance(room, str) or room not in ROOM_NAMES:
        raise ValueError(f"Invalid room ID: {room!r}")


def calculate_pm25(current_pm25, emission=0.0, purifying=False, *, purifying_seconds=60):
    """Calculate one minute of emissions, natural decay, and optional purification in one room."""
    _nonnegative_number(current_pm25, "current concentration")
    _nonnegative_number(emission, "emission")
    if type(purifying) is not bool:
        raise ValueError("purifying must be True or False.")
    _nonnegative_number(purifying_seconds, "purification time")
    if purifying_seconds > 60:
        raise ValueError("Purification time cannot exceed 60 seconds per minute.")
    increased = current_pm25 + emission
    if not math.isfinite(increased):
        raise ValueError("The sum of concentration and emission is too large.")
    after_natural = increased - max(increased - NATURAL_BASELINE, 0) * NATURAL_DECAY_RATE
    if purifying and purifying_seconds > 0:
        # 60 seconds gives a 5% reduction. For mid-minute arrivals and departures, count only time spent purifying.
        multiplier = (1 - PURIFICATION_RATE) ** (purifying_seconds / 60)
        return max(PURIFICATION_FLOOR, after_natural * multiplier)
    return after_natural


@dataclass(frozen=True)
class PollutionEvent:
    """Activity interval [start_minute, end_minute), measured in minutes since midnight."""

    room: str
    activity: str
    start_minute: int
    end_minute: int

    def __post_init__(self):
        _room(self.room)
        if not isinstance(self.activity, str) or self.activity not in ACTIVITY_RATES:
            raise ValueError("Activity must be cooking, cleaning, or bedding.")
        _integer(self.start_minute, "start time")
        _integer(self.end_minute, "end time")
        if not self.start_minute < self.end_minute <= MINUTES_PER_DAY:
            raise ValueError("An activity must end after it starts and remain within minutes 0 to 1440.")

    def is_active(self, minute):
        return self.start_minute <= minute < self.end_minute


def generate_daily_events(seed=0, day_index=0, late_dinner=False):
    """Generate four daily activities with a local RNG, preserving global random state."""
    _integer(seed, "seed")
    _integer(day_index, "day_index")
    if type(late_dinner) is not bool:
        raise ValueError("late_dinner must be True or False.")
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
        start = rng.randint(earliest, latest)  # Both ends of the start window are inclusive
        duration = rng.randint(shortest, longest)
        events.append(PollutionEvent(room, activity, start, start + duration))
    return tuple(sorted(events, key=lambda event: (event.start_minute, event.room)))


class AirEnvironment:
    """One-day environment. Every room starts at a concentration of 10 at midnight.

    advance() advances exactly one minute. The environment does not reset automatically at 24:00.
    Create a new instance for each independent day.
    """

    def __init__(self, seed=0, day_index=0, late_dinner=False, events=None):
        _integer(seed, "seed")
        _integer(day_index, "day_index")
        if type(late_dinner) is not bool:
            raise ValueError("late_dinner must be True or False.")
        generated = events is None
        schedule = (generate_daily_events(seed, day_index, late_dinner)
                    if generated else tuple(events))
        if not all(isinstance(event, PollutionEvent) for event in schedule):
            raise ValueError("events must contain only PollutionEvent instances.")
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
        """Advance one minute and return the updated time.

        purifying_room selects a single room for the full minute, or None for no purification.
        Pass None during travel. The command applies only to this call.
        Supply it again on subsequent calls to advance() as needed.
        purification_seconds={room ID: seconds} accounts for partial minutes.
        Total purification across rooms is limited to 60 seconds for one purifier.
        purifying_room and purification_seconds are mutually exclusive.
        """
        if purifying_room is not None:
            _room(purifying_room)
        exposure = {}
        if purification_seconds is not None:
            if purifying_room is not None or not isinstance(purification_seconds, dict):
                raise ValueError("Specify either a single room or per-room purification times.")
            exposure = dict(purification_seconds)
            for room, seconds in exposure.items():
                _room(room)
                _nonnegative_number(seconds, "purification time")
            if sum(exposure.values()) > 60:
                raise ValueError("Total purification time across rooms cannot exceed 60 seconds per minute.")
        elif purifying_room is not None:
            exposure[purifying_room] = 60
        if self._minute >= MINUTES_PER_DAY:
            raise ValueError("The day has ended. Create a new instance for the next independent scenario.")
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
        """Return a reading for the current room supplied by the caller.

        The environment does not track coordinates. Pass the room at the actual position.
        Do not expose this method as an API for sampling unvisited rooms.
        Measurements are unavailable in doorways (None).
        The caller maintains observation history and prevents duplicate readings.
        """
        _room(current_room)
        return {"minute": self._minute, "room": current_room,
                "pm25": self._pm25[current_room]}

    def get_ground_truth(self):
        """Return ground truth for labels and evaluation. It includes unvisited rooms and must stay out of prediction inputs."""
        return {"minute": self._minute, "pm25": dict(self._pm25)}

    def get_scenario(self):
        """Return reproducibility settings and future events. Keep them out of app and policy observations."""
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
