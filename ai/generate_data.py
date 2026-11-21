import csv
import json
import random
from datetime import datetime
from pathlib import Path

from simulation import Simulator


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


def save_csv(filename, rows):
    """Save records to a CSV file."""
    with (OUTPUT / filename).open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)


# ---------- Data generation ----------

def generate():
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
            "scenario_day": day,
        }

        visit_rng = random.Random(VISIT_SEED + day)

        # Use Part B's environment, movement, sensing, and purification.
        sim = Simulator(
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

        samples.extend(daily_samples)

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
                observations.append({
                    **metadata,
                    "measured_at": clock(seconds),
                    "measured_at_seconds": seconds,
                    "source_minute": entry["source_minute"],
                    "room_id": entry["room"],
                    "measured_pm25": entry["pm25"],
                })

        print(
            f"Day {day}/60 complete: {pattern}",
            flush=True,
        )

    if len(truth) != 25920:
        raise ValueError("Unexpected ground-truth record count.")

    # Preserve previous data after successful simulation.
    if OUTPUT.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = ROOT / f"data_backup_{stamp}"

        OUTPUT.rename(backup)

        print("Previous data preserved at:", backup)

    OUTPUT.mkdir(parents=True)

    # ---------- Save datasets ----------

    datasets = [
        ("ground_truth.csv", truth),
        ("observations.csv", observations),
        ("ai_dataset.csv", samples),
        ("events.csv", events),
        ("actions.csv", actions),
    ]

    for filename, rows in datasets:
        save_csv(filename, rows)

    for split in ["train", "validation", "test"]:
        selected = [
            row for row in samples
            if row["split"] == split
        ]

        save_csv(f"{split}.csv", selected)

        print(split, len(selected), "rows")

    # Store shared environment settings and maps for reproduction.
    config = {
        "version": "simulator-generator-v2",
        "run_id": RUN_ID,
        "days": 60,
        "event_seed": EVENT_SEED,
        "event_day_index": "scenario_day - 1",
        "visit_seed_base": VISIT_SEED,
        "visit_seed_rule": "visit_seed_base + scenario_day",
        "shifted_test_days": SHIFTED_TEST_DAYS,
        "patrol_interval": "arrival-to-arrival including travel",
        "timestamp_format":
            "HH:MM; exact minute-aligned patrol measurements",
        "features": [
            "room_id",
            "hour",
            "minute",
            "last_measured_pm25",
            "minutes_since_measurement",
        ],
        "label": "target_pm25_30min",
        "scenarios": scenarios,
    }

    (OUTPUT / "config.json").write_text(
        json.dumps(
            config,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Ground-truth records:", len(truth))
    print("Observation records:", len(observations))
    print("AI samples:", len(samples))
    print("Output directory:", OUTPUT)


if __name__ == "__main__":
    generate()