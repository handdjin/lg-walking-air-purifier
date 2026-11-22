"""Compare automatic control with fixed departures on the same simulated day."""
import argparse

from ai.predict import Predictor
from backend.runtime import SimulationRuntime
from simulation import Simulator
from simulation.environment import ROOM_NAMES, generate_daily_events
from simulation.simulator import PURIFY_ON


PATROL_ROOMS = ("living_room", "kitchen", "bedroom")
DEPARTURE_INTERVAL_SECONDS = 20 * 60


def fixed_patrol_tick(simulator):
    seconds = simulator.get_state()["simulation_time_seconds"]
    departure, remainder = divmod(seconds, DEPARTURE_INTERVAL_SECONDS)
    if departure and remainder == 0:
        simulator.move_to(PATROL_ROOMS[departure % len(PATROL_ROOMS)])
    return simulator.step()


def evaluate_day(simulator, tick):
    """Count minute-end PM readings above the threshold and completed trips."""
    above_threshold = dict.fromkeys(ROOM_NAMES, 0)
    state = simulator.start()
    while not state["finished"]:
        state = tick()
        if state["simulation_time_seconds"] % 60 == 0:
            for room, pm25 in simulator.get_ground_truth()["pm25"].items():
                if pm25 > PURIFY_ON:
                    above_threshold[room] += 1
    arrivals = sum(event["type"] == "arrival" for event in simulator.get_history())
    return above_threshold, arrivals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--day-index", type=int, default=0)
    args = parser.parse_args()
    if args.seed < 0 or args.day_index < 0:
        parser.error("--seed and --day-index must be nonnegative")

    events = generate_daily_events(args.seed, args.day_index)
    options = dict(seed=args.seed, day_index=args.day_index, events=events)
    auto = Simulator(**options)
    patrol = Simulator(**options)
    runtime = SimulationRuntime(auto, Predictor())
    auto_minutes, auto_trips = evaluate_day(auto, runtime.tick)
    patrol_minutes, patrol_trips = evaluate_day(patrol, lambda: fixed_patrol_tick(patrol))

    print(f"seed={args.seed}, day_index={args.day_index}, 24 simulated hours")
    print("| Metric | AI control | Fixed 20-minute patrol |")
    print("| --- | ---: | ---: |")
    for room, name in ROOM_NAMES.items():
        print(f"| {name} PM2.5 above {PURIFY_ON} (minutes) | {auto_minutes[room]} | {patrol_minutes[room]} |")
    print(f"| Completed trips (count) | {auto_trips} | {patrol_trips} |")


if __name__ == "__main__":
    main()
