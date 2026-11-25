"""Compare automatic control with fixed departures on the same simulated day."""
import argparse

from ai.predict import Predictor, predict_from_simulator
from simulation import Simulator
from simulation.controller import decide_and_move
from simulation.environment import ROOM_NAMES, generate_daily_events
from simulation.simulator import PURIFY_ON


PATROL_ROOMS = ("living_room", "kitchen", "bedroom")
DEPARTURE_INTERVAL_SECONDS = 20 * 60
AI_MOVE_THRESHOLD = 20


def ai_tick(simulator, predictor):
    """Run the one-day AI baseline with initial visits and ten-minute forecasts."""
    state = simulator.get_state()
    if not state["remaining_steps"]:
        for room in PATROL_ROOMS:
            if state["observations"][room]["pm25"] is None:
                state = simulator.move_to(room)
                break

    if state["simulation_time_seconds"] % 600 == 0:
        forecast = predict_from_simulator(predictor, simulator)
        if forecast["status"] == "ok" and not state["remaining_steps"]:
            decide_and_move(simulator, forecast["predictions"], threshold=AI_MOVE_THRESHOLD)
    return simulator.step()


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
    predictor = Predictor()
    auto_minutes, auto_trips = evaluate_day(auto, lambda: ai_tick(auto, predictor))
    patrol_minutes, patrol_trips = evaluate_day(patrol, lambda: fixed_patrol_tick(patrol))

    print(f"seed={args.seed}, day_index={args.day_index}, 가상 시간 24시간")
    print("| 평가 항목 | AI 자동 이동 | 20분 고정 순찰 |")
    print("| --- | ---: | ---: |")
    for room, name in ROOM_NAMES.items():
        print(f"| {name} PM2.5 {PURIFY_ON} 초과 (분) | {auto_minutes[room]} | {patrol_minutes[room]} |")
    print(f"| 이동 완료 (회) | {auto_trips} | {patrol_trips} |")


if __name__ == "__main__":
    main()
