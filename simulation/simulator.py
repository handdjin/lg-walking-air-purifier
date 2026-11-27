"""Coordinate movement, time, measurements, and purification in a fixed update order."""

from collections import deque
from copy import deepcopy

from .environment import AirEnvironment, MINUTES_PER_DAY, ROOM_NAMES
from .house_map import coordinate, load_house_map
from .pathfinding import DStarLite, NoPathError


TICK_SECONDS = 10
MEASUREMENT_INTERVAL_SECONDS = 10 * 60
PURIFY_ON = 20
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
        self._initial_day_index = day_index
        self._initial_late_dinner = late_dinner
        self.reset()

    def reset(self):
        """Reset position, destination, route, time, environment, and observations."""
        self.simulation_day = 1
        self.previous_days = deque(maxlen=14)
        self._environment_options["day_index"] = self._initial_day_index
        self._environment_options["late_dinner"] = self._initial_late_dinner
        return self._begin_day()

    def next_day(self, *, late_dinner=None):
        """Carry measured history into the next simulated day of this home.

        late_dinner optionally changes the generated schedule from this day on.
        """
        if not self.get_state()["finished"]:
            raise ValueError("The current day is still running.")
        if late_dinner is not None:
            if type(late_dinner) is not bool:
                raise ValueError("late_dinner must be True or False.")
            self._environment_options["late_dinner"] = late_dinner
        readings = {room: [] for room in ROOM_NAMES}
        for entry in self._history:
            if entry["type"] == "measurement" and entry["time_seconds"] < 86400:
                readings[entry["room"]].append((entry["time_seconds"], entry["pm25"]))
        self.previous_days.append(readings)
        self.simulation_day += 1
        self._environment_options["day_index"] += 1
        self._begin_day()
        return self.start()

    def _begin_day(self):
        self.last_arrival_seconds = None
        environment = AirEnvironment(**self._environment_options)
        self._position = self._map.start
        self._destination = None
        self._path = deque()
        self._planner = None      # D* Lite instance kept for the active route
        self._blocked = set()     # Walkable cells closed at run time
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
            "simulation_day": self.simulation_day,
            "current_room": room,
            "room_name": self._map.rooms[room].name if room else None,
            "position": list(self._position),
            "destination": self._destination,
            "status": "moving" if self._path else ("purifying" if self._purifying else "idle"),
            "remaining_path": [list(point) for point in self._path],
            "blocked_cells": [list(cell) for cell in sorted(self._blocked)],
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

        path = self._plan(self._map.rooms[room].target).path()
        return (len(path) - 1) * self._tick_seconds

    def _plan(self, goal):
        """Create a D* Lite planner from the current position that avoids blocked cells."""
        planner = DStarLite(self._map, self._position, goal)
        planner.update_cells(blocked=self._blocked)
        return planner

    def set_blocked(self, cells, blocked=True):
        """Close (blocked=True) or reopen (blocked=False) walkable cells at run time.

        Room targets and the purifier's current cell cannot be closed. Invalid input
        preserves the state. During travel, D* Lite repairs the remaining route from
        the current cell. If no route remains, the purifier stops where it is.
        """
        if not isinstance(blocked, bool):
            raise ValueError("blocked must be True or False.")
        cells = [coordinate(cell) for cell in cells]
        targets = {room.target for room in self._map.rooms.values()}
        for cell in cells:
            if not self._map.is_walkable(cell):
                raise ValueError(f"{list(cell)} is not a walkable map cell.")
            if blocked and (cell in targets or cell == self._position):
                raise ValueError(f"{list(cell)} is a room target or the purifier's position.")
        changed = sorted(set(cells) - self._blocked if blocked else set(cells) & self._blocked)
        if not changed:
            return self.get_state()
        if blocked:
            self._blocked.update(changed)
        else:
            self._blocked.difference_update(changed)
        self._record("cells_blocked" if blocked else "cells_cleared",
                     cells=[list(cell) for cell in changed])
        if self._planner is not None:
            if blocked:
                self._planner.update_cells(blocked=changed)
            else:
                self._planner.update_cells(cleared=changed)
            self._replan()
        return self.get_state()

    def _replan(self):
        """Repair the active route after cells changed, or stop if it is cut off."""
        try:
            route = deque(self._planner.path()[1:])
        except NoPathError:
            self._path = deque()
            self._planner = None
            self._record("route_blocked", destination=self._destination,
                         position=list(self._position))
            self._measure_current_room("route_blocked")
            return
        if route != self._path:
            self._path = route
            self._record("replanned", destination=self._destination,
                         remaining_steps=len(route))

    def move_to(self, room: str):
        """Reserve a route. Invalid and unreachable destinations preserve the current state."""
        if not isinstance(room, str) or room not in self._map.rooms:
            raise ValueError(f"Invalid room ID: {room!r}")
        if self._seconds >= MINUTES_PER_DAY * 60:
            raise ValueError("The day has ended. Call reset() before moving.")
        planner = self._plan(self._map.rooms[room].target)
        path = planner.path()
        # Preserve movement and purification state until route planning succeeds.
        if path[1:]:
            self._set_purifying(False, "move_requested")
        self._destination = room
        self._path = deque(path[1:])
        self._planner = planner if self._path else None
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
            if self._path:
                self._planner.move_start(self._position)
            else:
                self._planner = None
        self._seconds = next_seconds
        if moving and not self._path:
            self.last_arrival_seconds = self._seconds
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
