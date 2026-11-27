"""Compare backend Auto Mode with fixed departures on the same simulated day."""
import argparse

from simulation import Simulator
from simulation.controller import choose_destination
from simulation.environment import ROOM_NAMES, generate_daily_events
from simulation.simulator import PURIFY_ON


PATROL_ROOMS = ("living_room", "kitchen", "bedroom")
DEPARTURE_INTERVAL_SECONDS = 20 * 60
DECISION_INTERVAL_SECONDS = 10 * 60
AI_MOVE_THRESHOLD = 20
ARRIVAL_DWELL_SECONDS = 10 * 60


def stale_limit_seconds(simulation_day):
    """Revisit limit for the oldest reading: 120 minutes through day 7, then 180."""
    return (120 if simulation_day <= 7 else 180) * 60


class AutoModePolicy:
    """Backend Auto Mode without the database or HTTP layer.

    Mirrors initial_patrol() and auto_decision() in backend/main.py. Keep both in sync
    when the backend rules change. Forecasts use simulator.previous_days, which holds
    the same up to 14 previous days of measurements as the backend's SQLite store.
    """

    def __init__(self, predictor, *, forecast=None):
        # forecast(simulator) defaults to ai.predict.predict_from_simulator with this predictor.
        self.predictor = predictor
        self._forecast = forecast
        self.counts = {"forecast_moves": 0, "stale_revisits": 0}
        self._day = None

    def tick(self, simulator):
        if simulator.simulation_day != self._day:
            # The backend clears its forecast and decision when the day changes.
            self._day = simulator.simulation_day
            self.latest_decision = None
            self.last_prediction_seconds = None
        self._initial_patrol(simulator)
        self._decide(simulator)
        return simulator.step()

    def _predict(self, simulator):
        if self._forecast is not None:
            return self._forecast(simulator)
        # Imported here so the simulation package and its tests need no ML libraries.
        from ai.predict import predict_from_simulator

        return predict_from_simulator(self.predictor, simulator)

    def _initial_patrol(self, simulator):
        """Visit rooms that have not been measured today."""
        state = simulator.get_state()
        if state["remaining_steps"]:
            return
        for room in PATROL_ROOMS:
            if state["observations"][room]["pm25"] is None:
                simulator.move_to(room)
                return

    def _decide(self, simulator):
        state = simulator.get_state()
        if state["finished"]:
            return
        seconds = state["simulation_time_seconds"]

        if seconds % DECISION_INTERVAL_SECONDS == 0 and self.last_prediction_seconds != seconds:
            forecast = self._predict(simulator)
            self.last_prediction_seconds = seconds
            self.latest_decision = None
            if forecast["status"] == "ok" and not state["remaining_steps"]:
                self.latest_decision = choose_destination(
                    simulator, forecast["predictions"], threshold=AI_MOVE_THRESHOLD)

        decision = self.latest_decision
        if (not decision or state["remaining_steps"]
                or decision["decided_at_seconds"] != seconds - seconds % DECISION_INTERVAL_SECONDS):
            return
        arrival = simulator.last_arrival_seconds
        if arrival is not None and seconds - arrival < ARRIVAL_DWELL_SECONDS:
            return
        if decision["action"] == "move" and seconds % DECISION_INTERVAL_SECONDS == 0:
            simulator.move_to(decision["target_room"])
            self.counts["forecast_moves"] += 1
            return

        # Stagger stale-reading checks within the 10-minute window by day.
        phase = ((simulator.simulation_day - 1) * 3 % 10) * 60
        if (decision["action"] == "wait" and seconds % DECISION_INTERVAL_SECONDS == phase
                and not state["is_purifying"]):
            ages = {room: reading["age_seconds"] for room, reading in state["observations"].items()
                    if room != state["current_room"] and reading["age_seconds"] is not None}
            if ages:
                room = max(ages, key=ages.get)
                if ages[room] >= stale_limit_seconds(simulator.simulation_day):
                    simulator.move_to(room)
                    self.latest_decision = {**decision, "action": "move",
                                            "reason": "stale_measurement", "target_room": room}
                    self.counts["stale_revisits"] += 1


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
    from ai.predict import Predictor

    policy = AutoModePolicy(Predictor())
    auto_minutes, auto_trips = evaluate_day(auto, lambda: policy.tick(auto))
    patrol_minutes, patrol_trips = evaluate_day(patrol, lambda: fixed_patrol_tick(patrol))

    print(f"seed={args.seed}, day_index={args.day_index}, 가상 시간 24시간")
    print("| 평가 항목 | AI 자동 이동 | 20분 고정 순찰 |")
    print("| --- | ---: | ---: |")
    for room, name in ROOM_NAMES.items():
        print(f"| {name} PM2.5 {PURIFY_ON} 초과 (분) | {auto_minutes[room]} | {patrol_minutes[room]} |")
    print(f"| 이동 완료 (회) | {auto_trips} | {patrol_trips} |")


if __name__ == "__main__":
    main()
