"""python3 -m simulation.demo shows the route from the living room to the kitchen, bedroom, and back."""

import argparse
import time

from .simulator import Simulator


def show(simulator):
    state = simulator.get_state()
    location = state["room_name"] or "Passing through doorway"
    print(simulator.render_map())
    print(f"Location: {location} {state['position']} | Status: {state['status']}"
          f" | Steps remaining: {state['remaining_steps']}"
          f" | Simulated time: {state['simulation_time_seconds']} s\n")


def main():
    parser = argparse.ArgumentParser(description="2D navigation between rooms, one cell at a time.")
    parser.add_argument("--delay", type=float, default=0,
                        help="Real seconds between frames. This controls the display speed only.")
    args = parser.parse_args()
    if not 0 <= args.delay <= 5:
        parser.error("--delay must be between 0 and 5 seconds.")
    simulator = Simulator()
    simulator.start()
    print("# wall | X obstacle | D doorway | . floor | R purifier")
    print("Left: living room / upper right: kitchen / lower right: bedroom\n")
    show(simulator)
    for room in ("kitchen", "bedroom", "living_room"):
        print(f"Requested destination: {room}")
        state = simulator.move_to(room)
        while state["status"] == "moving":
            if args.delay:
                time.sleep(args.delay)
            state = simulator.step()
            show(simulator)
        print(f"Arrived at: {state['room_name']}\n")
    try:
        simulator.move_to("bathroom")
    except ValueError as error:
        print(f"Invalid move request: {error}")
    print(f"Position after error: {simulator.get_state()['position']}")


if __name__ == "__main__":
    main()
