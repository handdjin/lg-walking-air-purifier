"""python3 -m simulation.environment_demo demonstrates the shared environmental calculations."""

from .environment import AirEnvironment, PollutionEvent, calculate_pm25


def main():
    print("Rule check: initial concentration 30, no emissions")
    print(f"Natural decay only: {calculate_pm25(30):.2f}")
    print(f"Natural decay and purification: {calculate_pm25(30, purifying=True):.2f}\n")

    scenario = AirEnvironment(seed=42).get_scenario()
    print("seed=42 daily activities (for ground truth)")
    for event in scenario["events"]:
        start, end = event["start_minute"], event["end_minute"]
        print(f"{event['room']:12} {event['activity']:8} "
              f"{start // 60:02}:{start % 60:02}~{end // 60:02}:{end % 60:02}")

    # Fix cooking at 00:00–00:10 for this short comparison.
    # The default randomized schedule is unchanged.
    events = (PollutionEvent("kitchen", "cooking", 0, 10),)
    natural = AirEnvironment(events=events)
    cleaned = AirEnvironment(events=events)
    print("\nDemo: cooking 00:00–00:10 / kitchen purification from 00:10")
    print("Elapsed minutes | No purification | Kitchen purification")
    for minute in range(31):
        if minute % 5 == 0:
            a = natural.get_ground_truth()["pm25"]["kitchen"]
            b = cleaned.get_ground_truth()["pm25"]["kitchen"]
            print(f"{minute:7} | {a:9.2f} | {b:9.2f}")
        if minute < 30:
            natural.advance()
            cleaned.advance(purifying_room="kitchen" if minute >= 10 else None)
    print("\nThis comparison isolates the purification calculation from automatic control and navigation.")


if __name__ == "__main__":
    main()
