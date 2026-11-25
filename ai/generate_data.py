import csv
import json
import random
from collections import deque
from tempfile import TemporaryDirectory
from datetime import datetime
from pathlib import Path

from simulation import Simulator
from simulation.environment import PollutionEvent
from ai.predict import FEATURES, HISTORY_FEATURES, recent_features

HOMES = {
    "original": None,
    "late_evening": [("kitchen", "cooking", 570, 630), ("kitchen", "cooking", 1305, 1335), ("living_room", "cleaning", 480, 510), ("bedroom", "bedding", 630, 660)],
    "early_five": [("kitchen", "cooking", 285, 315), ("kitchen", "cooking", 1005, 1035),
                   ("living_room", "cleaning", 405, 435), ("bedroom", "bedding", 345, 375)],
    "noon_night": [("kitchen", "cooking", 705, 735), ("kitchen", "cooking", 1365, 1395),
                   ("living_room", "cleaning", 885, 915), ("bedroom", "bedding", 705, 735)],
    "one_am": [("kitchen", "cooking", 45, 75), ("kitchen", "cooking", 825, 855),
               ("living_room", "cleaning", 1305, 1335), ("bedroom", "bedding", 1005, 1035)],
    "ten_am": [("kitchen", "cooking", 585, 615), ("kitchen", "cooking", 945, 975),
               ("living_room", "cleaning", 45, 75), ("bedroom", "bedding", 1365, 1395)],
}


# ---------- Generation settings ----------

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "data"

ROOMS = ["living_room", "kitchen", "bedroom"]

EVENT_SEED = 100
VISIT_SEED = 200

# Confirm these days with Part B.
SHIFTED_TEST_DAYS = [55, 56, 57]

RUN_ID = "run_simulator_v2"
DAY_SECONDS = 86400


# ---------- Output helpers ----------

def clock(seconds):
    """Keep HH:MM compatibility without rounding timestamps."""
    if seconds % 60 != 0:
        raise ValueError(
            "This schedule requires minute-aligned measurements."
        )

    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}"


def append_csv(folder, filename, rows):
    """Save records to a CSV file."""
    path = folder / filename
    new_file = not path.exists()
    with path.open(
        "a",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
        )
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


# ---------- Data generation ----------

def generate_home(home_id, windows, seed, folder):
    previous_days = deque(maxlen=14)
    truth = []
    observations = []
    samples = []
    events = []
    actions = []
    scenarios = []

    for day in range(1, 61):
        pattern = ["basic", "slow", "irregular"][(day - 1) % 3]

        if day <= 42:
            split = "train"
        elif day <= 51:
            split = "validation"
        else:
            split = "test"

        metadata = {
            "run_id": RUN_ID,
            "home_id": home_id,
            "scenario_day": day,
        }

        visit_rng = random.Random(VISIT_SEED + day)

        # Use Part B's environment, movement, sensing, and purification.
        rng = random.Random(seed + day)
        activities = []
        for room, activity, low, high in windows or ():
            start = rng.randint(low, high)
            duration = rng.randint(10, 20) if activity == "cooking" else rng.randint(5, 10)
            activities.append(PollutionEvent(room, activity, start, start + duration))
        sim = Simulator(
            events=activities if windows is not None else None,
            seed=EVENT_SEED,
            day_index=day - 1,
            late_dinner=day in SHIFTED_TEST_DAYS,
        )

        scenario = sim.get_scenario()

        scenarios.append({
            **metadata,
            "scenario": scenario,
            "map": sim.get_map(),
        })

        # Store event schedules for auditing, not as model inputs.
        for event in scenario["events"]:
            events.append({
                **metadata,
                "room_id": event["room"],
                "activity": event["activity"],
                "start": clock(event["start_minute"] * 60),
                "end": clock(event["end_minute"] * 60),
            })

        daily_truth = {}
        daily_samples = []

        room_index = 0
        departure = None
        arrival_due = None
        target_room = None

        state = sim.start()

        while state["simulation_time_seconds"] < DAY_SECONDS:
            seconds = state["simulation_time_seconds"]

            # Confirm arrival before scheduling the next visit.
            if arrival_due is not None and seconds == arrival_due:
                if (
                    state["remaining_steps"]
                    or state["current_room"] != target_room
                ):
                    raise ValueError(
                        "Actual arrival does not match the patrol schedule."
                    )

                room_index = (room_index + 1) % len(ROOMS)

                arrival_due = None
                target_room = None
                departure = None

            # Record after measurements and before new departure commands.
            if seconds % 600 == 0:
                actual = sim.get_ground_truth()

                # Hidden ground truth is used only for labels and evaluation.
                for room in ROOMS:
                    value = actual["pm25"][room]

                    daily_truth[(seconds, room)] = value

                    truth.append({
                        **metadata,
                        "timestamp": clock(seconds),
                        "room_id": room,
                        "true_pm25": value,
                    })

                # Model inputs use observations only.
                readings = state["observations"]

                complete = all(
                    readings[room]["pm25"] is not None
                    for room in ROOMS
                )

                target_within_day = seconds + 1800 < DAY_SECONDS

                if complete and target_within_day:
                    for room in ROOMS:
                        reading = readings[room]
                        measured = reading["measured_at_seconds"]

                        daily_samples.append({
                            **metadata,
                            "prediction_time": clock(seconds),
                            "target_time": clock(seconds + 1800),
                            "last_measured_at": clock(measured),
                            "patrol_pattern": pattern,
                            "split": split,
                            "room_id": room,
                            "hour": seconds // 3600,
                            "minute": seconds % 3600 // 60,
                            "last_measured_pm25": reading["pm25"],
                            "minutes_since_measurement":
                                (seconds - measured) / 60,
                        })

            # Preserve arrival-to-arrival intervals, including travel.
            if arrival_due is None:
                if pattern == "basic":
                    gap = 10
                elif pattern == "slow":
                    gap = 20
                else:
                    gap = visit_rng.choice([10, 20, 30])

                arrival_due = seconds + gap * 60

                target_room = ROOMS[
                    (room_index + 1) % len(ROOMS)
                ]

                if arrival_due < DAY_SECONDS:
                    travel = sim.estimate_travel_seconds(target_room)

                    if travel <= 0 or travel > gap * 60:
                        raise ValueError(
                            "Travel time does not fit the patrol interval."
                        )

                    departure = arrival_due - travel

                    if departure % state["tick_seconds"]:
                        raise ValueError(
                            "Departure must align with simulator ticks."
                        )

            # Move early enough to reach the next room on schedule.
            if departure is not None and seconds == departure:
                sim.move_to(target_room)
                departure = None

            # Advance actual movement, environment, sensing, and purification.
            state = sim.step()

        # Attach same-day, 30-minute-ahead ground-truth labels.
        for row in daily_samples:
            hour, minute = map(
                int,
                row["target_time"].split(":"),
            )

            target_seconds = hour * 3600 + minute * 60

            row["target_pm25_30min"] = daily_truth[
                (target_seconds, row["room_id"])
            ]

            row.update(zip(HISTORY_FEATURES, recent_features(previous_days, row["room_id"], target_seconds // 60)))
        samples.extend(daily_samples)
        readings = {room: [] for room in ROOMS}

        # Collect the complete history once per day.
        for entry in sim.get_history():
            seconds = entry["time_seconds"]

            actions.append({
                **metadata,
                "time_seconds": seconds,
                "event_json": json.dumps(
                    entry,
                    ensure_ascii=False,
                ),
            })

            if (
                entry["type"] == "measurement"
                and seconds < DAY_SECONDS
            ):
                readings[entry["room"]].append((seconds, entry["pm25"]))
                observations.append({
                    **metadata,
                    "measured_at": clock(seconds),
                    "measured_at_seconds": seconds,
                    "source_minute": entry["source_minute"],
                    "room_id": entry["room"],
                    "measured_pm25": entry["pm25"],
                })

        previous_days.append(readings)

    if len(truth) != 25920:
        raise ValueError("Unexpected ground-truth record count.")
    datasets = [
        ("ground_truth.csv", truth),
        ("observations.csv", observations),
        ("ai_dataset.csv", samples),
        ("events.csv", events),
        ("actions.csv", actions),
    ]

    for filename, rows in datasets:
        append_csv(folder, filename, rows)

    for split in ["train", "validation", "test"]:
        selected = [
            row for row in samples
            if row["split"] == split
        ]

        append_csv(folder, f"{split}.csv", selected)

        print(split, len(selected), "rows")

    return scenarios


def generate():
    with TemporaryDirectory(dir=ROOT) as temp:
        folder = Path(temp) / "data"
        folder.mkdir()
        scenarios = []
        for index, (home, windows) in enumerate(HOMES.items()):
            scenarios.extend(generate_home(home, windows, 1000 + index * 100, folder))
            print(f"Generated {home}: 60 days", flush=True)
        config = {"homes": list(HOMES), "days_per_home": 60,
                  "features": FEATURES + HISTORY_FEATURES,
                  "label": "target_pm25_30min", "scenarios": scenarios}
        (folder / "config.json").write_text(json.dumps(config, indent=2))
        if OUTPUT.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            OUTPUT.rename(ROOT / f"data_backup_{stamp}")
        folder.rename(OUTPUT)


if __name__ == "__main__":
    generate()
