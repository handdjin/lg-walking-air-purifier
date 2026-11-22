"""python3 -m simulation.controller_demo: demonstrate destination selection with sample forecasts."""

from . import Simulator
from .controller import decide_and_move


def main():
    print("These sample values illustrate integration. They are not model predictions.")
    examples = [
        ("High risk in kitchen", {"living_room": 20, "kitchen": 60, "bedroom": 40}),
        ("High risk in bedroom", {"living_room": 20, "kitchen": 40, "bedroom": 60}),
        ("Current room selected", {"living_room": 60, "kitchen": 20, "bedroom": 20}),
        ("Low predictions in all rooms", {"living_room": 20, "kitchen": 20, "bedroom": 20}),
    ]
    for label, predictions in examples:
        sim = Simulator(events=())
        result = decide_and_move(sim, predictions)
        decision = result["decision"]
        print(f"\n{label}: {predictions}")
        for room, detail in decision["rooms"].items():
            print(f"  {room}: travel {detail['travel_seconds']} s, score {detail['score']:.2f}")
        print("Decision:", decision["action"], decision["target_room"], decision["reason"])
        sim.start()
        while sim.get_state()["remaining_steps"]:
            sim.step()
        state = sim.get_state()
        print("Result:", state["current_room"], state["position"],
              f"{state['simulation_time_seconds']} simulated seconds")


if __name__ == "__main__":
    main()
