"""python3 -m simulation.integration_demo: compare movement, air quality, and automatic purification."""

from . import Simulator
from .environment import PollutionEvent


def main():
    # Use an event for a quick demonstration while preserving the default daily schedule.
    events = (PollutionEvent("kitchen", "cooking", 0, 20),)
    scenarios = [Simulator(events=()), Simulator(events=events), Simulator(events=events)]
    for simulator in scenarios:
        simulator.start()
    cleaned = scenarios[2]
    print("Demo: cooking in the kitchen from 00:00 to 00:20, leaving the living room for the kitchen at 00:10")
    print("These concentrations are internal ground truth for verification. The app displays actual sensor readings.")
    print("Simulated seconds | No pollution | Cooking, no visit | Cooking, visit and purify | Purifier status")
    for seconds in range(0, 3601, 10):
        if seconds == 600:
            cleaned.move_to("kitchen")
        if seconds in (0, 600, 700, 1200, 1800, 2400, 3600):
            values = [s.get_ground_truth()["pm25"]["kitchen"] for s in scenarios]
            print(f"{seconds:7} | {values[0]:9.2f} | {values[1]:14.2f} | "
                  f"{values[2]:14.2f} | {cleaned.get_state()['status']}")
        if seconds < 3600:
            for simulator in scenarios:
                simulator.step()
    print("\nMeasurement and automatic purification history:")
    for entry in cleaned.get_history():
        if entry["type"] in ("measurement", "purification_on", "purification_off"):
            print(entry)
    paused = cleaned.pause()
    assert cleaned.step() == paused
    print("\nPause check: calling step() preserves position, time, and air quality.")
    reset = cleaned.reset()
    assert reset["simulation_time_seconds"] == 0 and reset["destination"] is None
    print("Reset check:", reset)


if __name__ == "__main__":
    main()
