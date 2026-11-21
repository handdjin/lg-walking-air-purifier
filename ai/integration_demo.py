"""Run with: python -m ai.integration_demo."""

import json

from ai.predict import Predictor, predict_from_simulator
from simulation import Simulator
from simulation.controller import decide_and_move
from simulation.environment import PollutionEvent


def advance_to(sim, seconds):
    """Advance the running simulator to a scheduled time."""
    state = sim.get_state()

    if (
        seconds < state["simulation_time_seconds"]
        or seconds % state["tick_seconds"]
    ):
        raise ValueError("Invalid scheduled time.")

    while state["simulation_time_seconds"] < seconds:
        state = sim.step()

    return state


def arrive_at(sim, room, seconds):
    """Travel early enough to arrive at the requested time."""
    departure = seconds - sim.estimate_travel_seconds(room)

    advance_to(sim, departure)
    sim.move_to(room)

    state = advance_to(sim, seconds)

    if state["remaining_steps"] or state["current_room"] != room:
        raise ValueError("Scheduled arrival failed.")

    return state


def prepare_scenario(early_breakfast):
    """Create observation histories through actual simulation."""
    breakfast = (490, 510) if early_breakfast else (540, 550)

    events = (
        PollutionEvent("kitchen", "cooking", *breakfast),
        PollutionEvent("kitchen", "cooking", 1080, 1090),
        PollutionEvent("living_room", "cleaning", 780, 785),
        PollutionEvent("bedroom", "bedding", 540, 545),
    )

    sim = Simulator(events=events)
    sim.start()

    rooms = ["living_room", "kitchen", "bedroom"]

    # Perform a regular patrol through 08:00.
    for visit in range(1, 49):
        arrive_at(
            sim,
            rooms[visit % 3],
            visit * 600,
        )

    # Use the same final visits in both scenarios.
    arrive_at(sim, "kitchen", 510 * 60)
    arrive_at(sim, "bedroom", 515 * 60)
    arrive_at(sim, "living_room", 520 * 60)

    return sim


def main():
    predictor = Predictor()
    results = []

    for early in [False, True]:
        sim = prepare_scenario(early)

        state = sim.get_state()
        forecast = predict_from_simulator(predictor, sim)

        if forecast["status"] != "ok":
            raise ValueError(forecast["status"])

        response = decide_and_move(
            sim,
            forecast["predictions"],
        )

        decision = response["decision"]

        while sim.get_state()["remaining_steps"]:
            sim.step()

        results.append({
            "scenario": (
                "breakfast_finished"
                if early
                else "breakfast_starts_at_09_00"
            ),
            "reference_time": "08:40",
            "observations": state["observations"],
            "forecast": forecast,
            "decision": decision,
            "final_room": sim.get_state()["current_room"],
            "final_time_seconds":
                sim.get_state()["simulation_time_seconds"],
        })

    print(json.dumps(results, indent=2, ensure_ascii=False))

    print(
        "Targets:",
        [result["decision"]["target_room"] for result in results],
    )

    print(
        "Actual predictions and simulated observations were used; "
        "no accuracy claim is made."
    )


if __name__ == "__main__":
    main()