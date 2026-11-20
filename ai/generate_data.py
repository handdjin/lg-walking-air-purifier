import csv
import json
import random
from pathlib import Path


# ---------- Generation settings ----------

ROOMS = ["living_room", "kitchen", "bedroom"]

OUTPUT = Path(__file__).resolve().parent / "data"

EVENT_SEED = 100
VISIT_SEED = 200

# Confirm these days with Part B.
SHIFTED_TEST_DAYS = [55, 56, 57]

RUN_ID = "run_001"


# ---------- Shared air quality calculation ----------

def step_pm25(current_pm25, event_increase, purifying):
    """Calculate a room's concentration one minute later."""
    value = current_pm25 + event_increase

    value -= max(value - 10, 0) * 0.01

    if purifying:
        value = max(5, value * 0.95)

    return value


# ---------- Output helpers ----------

def clock(minute):
    """Convert minutes since midnight to an HH:MM string."""
    return f"{minute // 60:02d}:{minute % 60:02d}"


def save_csv(filename, rows):
    """Save records to a CSV file."""
    with (OUTPUT / filename).open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)


# ---------- Data generation ----------

def generate():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    ground_truth = []
    observations = []
    ai_samples = []
    event_records = []

    for day in range(1, 61):
        # Use independent random generators for events and visits.
        event_rng = random.Random(EVENT_SEED + day)
        visit_rng = random.Random(VISIT_SEED + day)

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

        # Represent time as minutes since midnight.
        # 1080 = 18:00, 1200 = 20:00, 1320 = 22:00
        if day in SHIFTED_TEST_DAYS:
            dinner_range = (1200, 1320)
        else:
            dinner_range = (1080, 1200)

        # Room, activity, start range, duration range, increase per minute
        event_specs = [
            ("kitchen", "breakfast", 420, 540, 10, 20, 3),
            ("kitchen", "dinner", *dinner_range, 10, 20, 3),
            ("living_room", "cleaning", 780, 1020, 5, 10, 2),
            ("bedroom", "bedding", 420, 600, 5, 10, 2),
        ]

        daily_events = []

        for room, activity, lo, hi, dmin, dmax, increase in event_specs:
            start = event_rng.randint(lo, hi)
            duration = event_rng.randint(dmin, dmax)
            end = start + duration

            daily_events.append((room, start, end, increase))

            event_records.append({
                **metadata,
                "room_id": room,
                "activity": activity,
                "start": clock(start),
                "end": clock(end),
                "increase_per_minute": increase,
            })

        # Initialize each day independently.
        concentrations = {room: 10.0 for room in ROOMS}
        last_value = {room: None for room in ROOMS}
        last_time = {room: None for room in ROOMS}

        # Temporarily store today's ground truth and input samples.
        daily_truth = {}
        daily_samples = []

        room_index = 0
        next_arrival = 0
        purifying = False

        for minute in range(1440):
            arrival = minute == next_arrival

            # 1) Update the location on arrival.
            if arrival:
                if minute > 0:
                    room_index = (room_index + 1) % 3

                if pattern == "basic":
                    gap = 10
                elif pattern == "slow":
                    gap = 20
                else:
                    gap = visit_rng.choice([10, 20, 30])

                next_arrival = minute + gap

            current_room = ROOMS[room_index]

            # 2) Measure on arrival or periodically while staying.
            should_measure = (
                arrival
                or last_time[current_room] is None
                or minute - last_time[current_room] >= 10
            )

            if should_measure:
                measured = concentrations[current_room]

                last_value[current_room] = measured
                last_time[current_room] = minute

                observations.append({
                    **metadata,
                    "measured_at": clock(minute),
                    "room_id": current_room,
                    "measured_pm25": measured,
                })

                # 3) Update purification based on the measurement.
                if measured >= 35:
                    purifying = True
                elif measured <= 15:
                    purifying = False
                # Otherwise, retain the current state.

            # 4) Record ground truth and AI inputs every 10 minutes.
            if minute % 10 == 0:
                for room in ROOMS:
                    daily_truth[(minute, room)] = concentrations[room]

                    ground_truth.append({
                        **metadata,
                        "timestamp": clock(minute),
                        "room_id": room,
                        "true_pm25": concentrations[room],
                    })

                all_measured = all(
                    last_time[room] is not None
                    for room in ROOMS
                )

                target_within_day = minute + 30 < 1440

                if all_measured and target_within_day:
                    for room in ROOMS:
                        daily_samples.append({
                            **metadata,
                            "prediction_time": clock(minute),
                            "target_time": clock(minute + 30),
                            "last_measured_at": clock(last_time[room]),
                            "patrol_pattern": pattern,
                            "split": split,
                            "room_id": room,
                            "hour": minute // 60,
                            "minute": minute % 60,
                            "last_measured_pm25": last_value[room],
                            "minutes_since_measurement":
                                minute - last_time[room],
                        })

            # 5) Apply this minute's events and purification.
            for room in ROOMS:
                increase = sum(
                    amount
                    for event_room, start, end, amount in daily_events
                    if event_room == room and start <= minute < end
                )

                concentrations[room] = step_pm25(
                    concentrations[room],
                    increase,
                    purifying and room == current_room,
                )

        # Attach 30-minute-ahead labels after simulating the day.
        for row in daily_samples:
            hour, minute = map(int, row["target_time"].split(":"))
            target_minute = hour * 60 + minute

            row["target_pm25_30min"] = daily_truth[
                (target_minute, row["room_id"])
            ]

        ai_samples.extend(daily_samples)

    # ---------- Save files ----------

    save_csv("ground_truth.csv", ground_truth)
    save_csv("observations.csv", observations)
    save_csv("ai_dataset.csv", ai_samples)
    save_csv("events.csv", event_records)

    for split in ["train", "validation", "test"]:
        rows = [
            row for row in ai_samples
            if row["split"] == split
        ]
        save_csv(f"{split}.csv", rows)

    config = {
        "version": "1.0",
        "run_id": RUN_ID,
        "days": 60,
        "event_seed_base": EVENT_SEED,
        "visit_seed_base": VISIT_SEED,
        "daily_seed_rule": "seed_base + scenario_day",
        "shifted_test_days": SHIFTED_TEST_DAYS,
        "movement": "instant room change at arrival",
        "arrival_purification_state":
            "retain device state, then update from arrival measurement",
        "features": [
            "room_id",
            "hour",
            "minute",
            "last_measured_pm25",
            "minutes_since_measurement",
        ],
        "label": "target_pm25_30min",
        "rules": {
            "initial_pm25": 10,
            "natural_decay": 0.01,
            "purification_rate": 0.05,
            "purification_minimum": 5,
            "on_threshold": 35,
            "off_threshold": 15,
            "record_interval_minutes": 10,
            "prediction_horizon_minutes": 30,
        },
    }

    (OUTPUT / "config.json").write_text(
        json.dumps(config, indent=2),
        encoding="utf-8",
    )

    print("Data generation complete")
    print("Ground-truth records:", len(ground_truth), "rows")
    print("Observation records:", len(observations), "rows")
    print("AI samples:", len(ai_samples), "rows")

    for split in ["train", "validation", "test"]:
        count = sum(row["split"] == split for row in ai_samples)
        print(split, ":", count, "rows")

    print("Output directory:", OUTPUT)


if __name__ == "__main__":
    generate()
