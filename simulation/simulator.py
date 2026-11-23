"""Coordinate movement, time, measurements, and purification in a fixed update order."""

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
    """Start paused. After start(), each step() advances simulated time.

    The server determines when to call step(). The simulator has no thread or real-time timer.
    """

    def __init__(self, house_map=None, *, seed=0, day_index=0,
                 late_dinner=False, events=None, tick_seconds=TICK_SECONDS):
        self._map = house_map if house_map is not None else load_house_map()
        if set(self._map.rooms) != set(ROOM_NAMES):
            raise ValueError("Room IDs in the map and air quality environment must match.")
        if type(tick_seconds) is not int or tick_seconds <= 0 or 60 % tick_seconds:
            raise ValueError("tick_seconds must be a positive integer divisor of 60.")
        self._tick_seconds = tick_seconds
        self._environment_options = {
            "seed": seed, "day_index": day_index, "late_dinner": late_dinner,
            "events": None if events is None else tuple(events),
        }
        self.reset()

    def reset(self):
        """Reset position, destination, route, time, environment, and observations."""
        environment = AirEnvironment(**self._environment_options)
        self._position = self._map.start
        self._destination = None
        self._path = deque()
        self._environment = environment
        self._seconds = 0
        self._running = False
        self._purifying = False
        
        self._last_measurement_seconds = None
        self._exposure = {}  # 이번 1분 중 방별로 실제 정화한 가상 초
        self._observations = {room: None for room in self._map.rooms}
        
        self._history = []
        self._record("reset")
        self._measure_current_room("initial")
        return self.get_state()

    def start(self):
        """Enable time progression while preserving movement, idle, or purification state."""
        if self._seconds >= MINUTES_PER_DAY * 60:
            raise ValueError("The day has ended. Call reset() before starting.")
        if not self._running:
            self._running = True
            self._record("start")
        return self.get_state()

    def pause(self):
        """Pause time while preserving position, route, and purification settings."""
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
        """Measure only on arrival or while stationary, using the room at the actual coordinates."""
        room = self._map.room_at(self._position)
        if room is None or self._path:
            return
        previous = self._observations[room]
        if previous and previous["measured_at_seconds"] == self._seconds:
            return  # Avoid duplicate arrival and periodic readings at the same time in the same room
        sample = self._environment.sample_current_room(room)
        observation = {
            "pm25": sample["pm25"],
            "measured_at_seconds": self._seconds,
            "source_minute": sample["minute"],
        }
        self._observations[room] = observation
        self._last_measurement_seconds = self._seconds
        self._record("measurement", room=room, reason=reason, **observation)
        if sample["pm25"] >= PURIFY_ON:
            self._set_purifying(True, "measurement")
        elif sample["pm25"] <= PURIFY_OFF:
            self._set_purifying(False, "measurement")

    def get_map(self):
        return self._map.to_dict()

    def get_state(self):
        """Return app and policy state without hidden concentrations or future events."""
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
            "is_measuring": (
            self._last_measurement_seconds is not None
            and self._seconds - self._last_measurement_seconds < 20
            and not self._path
),
        }
    
    def estimate_travel_seconds(self, room):
        """Estimate travel time using the same path planner as move_to()."""
        if not isinstance(room, str) or room not in self._map.rooms:
            raise ValueError(f"Unknown room: {room!r}")

        if self._path:
            raise ValueError("Wait until the current route is complete.")

        path = find_path(
            self._map,
            self._position,
            self._map.rooms[room].target,
        )

        return (len(path) - 1) * self._tick_seconds

    def move_to(self, room: str):
        """Reserve a route. Invalid and unreachable destinations preserve the current state."""
        if not isinstance(room, str) or room not in self._map.rooms:
            raise ValueError(f"Invalid room ID: {room!r}")
        if self._seconds >= MINUTES_PER_DAY * 60:
            raise ValueError("The day has ended. Call reset() before moving.")
        path = find_path(self._map, self._position, self._map.rooms[room].target)
        # Preserve movement and purification state until route planning succeeds.
        if path[1:]:
            self._set_purifying(False, "move_requested")
        self._destination = room
        self._path = deque(path[1:])
        self._record("move_requested", destination=room)
        if not self._path:
            self._measure_current_room("arrival")
        return self.get_state()

    def step(self):
        """Advance one tick while running. Environmental time continues after arrival.

        Order: accumulate purification time, update the environment at minute boundaries, move one cell,
        update the clock, measure on arrival or when due, then decide whether to purify.
        The final travel interval does not count as purification in the destination room.
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
        """Return a copy of the recorded commands and measurement history."""
        return deepcopy(self._history)

    def get_ground_truth(self):
        """Return ground truth for labels and evaluation only. Exclude it from the public app state."""
        return self._environment.get_ground_truth()

    def get_scenario(self):
        """Return settings for reproducibility. Future events must stay out of app and forecast inputs."""
        return {**self._environment.get_scenario(), "tick_seconds": self._tick_seconds,
                "measurement_interval_seconds": MEASUREMENT_INTERVAL_SECONDS,
                "purify_on": PURIFY_ON, "purify_off": PURIFY_OFF}

    def render_map(self):
        rows = [list(row) for row in self._map.grid]
        x, y = self._position
        rows[y][x] = "R"
        return "\n".join("".join(row) for row in rows)
