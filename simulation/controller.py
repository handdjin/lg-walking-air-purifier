"""30-minute room forecasts drive the initial destination policy.

The caller supplies forecasts for all three rooms at the same reference time.
Training, inference, hidden concentrations, and future schedules are outside this policy.
"""

import math
from collections.abc import Mapping

from .house_map import HouseMap
from .pathfinding import DStarLite, NoPathError


def _number(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name} must be a finite, nonnegative number.")


def choose_destination(simulator, predictions, *, threshold=35.0,
                       travel_weight=1.0):
    """Return a destination decision without changing state.

    predictions: {room ID: predicted PM2.5 in 30 minutes}. Supply all three rooms,
    collecting initial readings first if an unmeasured room lacks a forecast.
    Score = predicted PM - travel minutes * travel_weight. Break ties by travel time, then room ID.
    An outstanding route prevents a new decision, even while paused.
    """
    _number(threshold, "candidate threshold")
    _number(travel_weight, "travel time weight")
    house = HouseMap(simulator.get_map())
    if not isinstance(predictions, Mapping) or set(predictions) != set(house.rooms):
        raise ValueError("Supply predictions for all three rooms on the map.")
    for room, value in predictions.items():
        _number(value, f"{room} prediction")
    state = simulator.get_state()
    if state["finished"]:
        raise ValueError("The day has ended. Call reset() before selecting a destination.")
    if state["remaining_steps"]:
        raise ValueError("A route is still active. Wait until arrival before selecting a destination.")

    rooms = {}
    candidates = []
    for room in sorted(house.rooms):
        predicted = float(predictions[room])
        # Stay in place when selecting the current room.
        try:
            if room == state["current_room"]:
                path = [tuple(state["position"])]
            else:
                # Use the same run-time blocked cells as Simulator.move_to().
                planner = DStarLite(house, state["position"], house.rooms[room].target)
                planner.update_cells(blocked=state.get("blocked_cells", ()))
                path = planner.path()
        except NoPathError:
            rooms[room] = {"predicted_pm25": predicted, "reachable": False,
                           "travel_steps": None, "travel_seconds": None,
                           "score": None, "eligible": False}
            continue
        steps = len(path) - 1
        seconds = steps * state["tick_seconds"]
        score = predicted - seconds / 60 * travel_weight
        if not math.isfinite(score):
            raise ValueError("Score exceeds the numeric range.")
        eligible = predicted >= threshold
        rooms[room] = {"predicted_pm25": predicted, "reachable": True,
                       "travel_steps": steps, "travel_seconds": seconds,
                       "score": score, "eligible": eligible}
        if eligible:
            candidates.append(room)

    target = min(candidates, key=lambda room: (
        -rooms[room]["score"], rooms[room]["travel_seconds"], room
    )) if candidates else None
    action = "wait" if target is None else (
        "stay" if target == state["current_room"] else "move")
    reason = ("all_predictions_below_threshold"
              if all(value < threshold for value in predictions.values())
              else "no_reachable_candidate") if target is None else (
                  "current_room_selected" if action == "stay" else "highest_score")
    return {"action": action, "target_room": target, "reason": reason,
            "decided_at_seconds": state["simulation_time_seconds"],
            "prediction_horizon_minutes": 30, "threshold": threshold,
            "travel_weight": travel_weight, "rooms": rooms}


def decide_and_move(simulator, predictions, *, threshold=35.0, travel_weight=1.0):
    """Choose a destination and reserve a route if another room is selected."""
    decision = choose_destination(simulator, predictions, threshold=threshold,
                                  travel_weight=travel_weight)
    if decision["action"] == "move":
        simulator.move_to(decision["target_room"])
    # start()/step() remain under caller control, preserving the current running or paused state.
    return {"decision": decision, "state": simulator.get_state()}
