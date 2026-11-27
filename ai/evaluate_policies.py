"""Run paired policy evaluation: python -m ai.evaluate_policies."""

import csv
import hashlib
import json
import statistics
import subprocess
from datetime import datetime
from pathlib import Path

import sklearn

from ai.predict import Predictor
from simulation import Simulator
from simulation.compare_patrol import (
    AI_MOVE_THRESHOLD,
    DEPARTURE_INTERVAL_SECONDS,
    AutoModePolicy,
    fixed_patrol_tick,
)
from simulation.environment import generate_daily_events
from simulation.simulator import PURIFY_ON


ROOT = Path(__file__).resolve().parent
ROOMS = ["living_room", "kitchen", "bedroom"]

EVENT_SEED = 9100

# Six normal days and three late-dinner days.
SCENARIOS = [(day, day >= 6) for day in range(9)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_csv(path, rows):
    with path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)


def evaluate_day(sim, tick, scenario_id, policy):
    """Use minute-end samples, matching Part B's evaluator."""
    sums = dict.fromkeys(ROOMS, 0.0)
    exceed = dict.fromkeys(ROOMS, 0)
    excess = dict.fromkeys(ROOMS, 0.0)

    curves = []
    distance = 0
    moving_seconds = 0
    max_age = 0

    state = sim.start()

    while not state["finished"]:
        previous_position = state["position"]

        state = tick()

        moved = sum(
            abs(a - b)
            for a, b in zip(previous_position, state["position"])
        )

        distance += moved

        if moved:
            moving_seconds += state["tick_seconds"]

        if state["simulation_time_seconds"] % 60 == 0:
            # Evaluation only: never provide these values to a policy.
            actual = sim.get_ground_truth()["pm25"]

            curves.append({
                "scenario": scenario_id,
                "policy": policy,
                "minute": state["environment_minute"],
                **actual,
            })

            for room in ROOMS:
                value = actual[room]

                sums[room] += value
                exceed[room] += int(value > PURIFY_ON)
                excess[room] += max(value - PURIFY_ON, 0)

                age = state["observations"][room]["age_seconds"]

                if age is not None:
                    max_age = max(max_age, age)

    if len(curves) != 1440:
        raise AssertionError(
            "Expected exactly 1440 minute-end samples."
        )

    history = sim.get_history()

    room_rows = []

    for room in ROOMS:
        room_rows.append({
            "scenario": scenario_id,
            "policy": policy,
            "room_id": room,
            "mean_pm25": sums[room] / 1440,
            "minutes_above_threshold": exceed[room],
            "excess_pm25_minutes": excess[room],
        })

    metrics = {
        "scenario": scenario_id,
        "policy": policy,
        "mean_pm25": sum(sums.values()) / (1440 * len(ROOMS)),
        "room_minutes_above_threshold": sum(exceed.values()),
        "excess_pm25_room_minutes": sum(excess.values()),
        "distance_cells": distance,
        "completed_trips": sum(
            event["type"] == "arrival"
            for event in history
        ),
        "move_requests": sum(
            event["type"] == "move_requested"
            for event in history
        ),
        "moving_minutes": moving_seconds / 60,
        "max_observation_age_minutes": max_age / 60,
    }

    return metrics, room_rows, curves


def main():
    model_metadata = json.loads(
        (ROOT / "artifacts" / "metrics.json").read_text(
            encoding="utf-8"
        )
    )

    expected_version = model_metadata["sklearn_version"]

    if sklearn.__version__ != expected_version:
        raise RuntimeError(
            f"Use scikit-learn {expected_version} to load this model; "
            f"current version is {sklearn.__version__}."
        )

    predictor = Predictor()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = ROOT / "evaluation_results" / timestamp
    output.mkdir(parents=True, exist_ok=False)

    project = ROOT.parent

    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=project,
        text=True,
    ).strip()

    source_files = [
        project / "simulation" / name
        for name in [
            "environment.py",
            "simulator.py",
            "controller.py",
            "compare_patrol.py",
            "pathfinding.py",
            "house_map.json",
        ]
    ]

    source_files += [
        ROOT / "predict.py",
        Path(__file__).resolve(),
    ]

    manifest = {
        "base_revision": revision,
        "sklearn_version": sklearn.__version__,
        "model_sha256": sha256(
            ROOT / "artifacts" / "uniform20_model.joblib"
        ),
        "source_sha256": {
            str(path.relative_to(project)): sha256(path)
            for path in source_files
        },
        "event_seed": EVENT_SEED,
        "scenarios": [
            {"day_index": day, "late_dinner": late}
            for day, late in SCENARIOS
        ],
        "threshold_operator": ">",
        "threshold": PURIFY_ON,
        "sampling": (
            "1440 minute-end samples, times 1 through 1440; "
            "1-minute approximation"
        ),
        "fixed_policy": (
            f"departure every {DEPARTURE_INTERVAL_SECONDS} seconds; "
            "living/kitchen/bedroom"
        ),
        "ai_policy": (
            "Backend Auto Mode (simulation.compare_patrol.AutoModePolicy): "
            "initial patrol, 10-minute forecasts, "
            f"movement threshold {AI_MOVE_THRESHOLD}, travel weight 1, "
            "10-minute stay after arrival, stale-reading revisit "
            "after 120 minutes (180 after day 7)"
        ),
        "day_sequence": (
            "scenarios run as consecutive days of one home per policy; "
            "Simulator.next_day() carries up to 14 previous days of "
            "measurements into the history features"
        ),
        "initialization": (
            "same initial state and living-room observation; "
            "each policy uses its own startup behavior"
        ),
    }

    # Check that complete event schedules are new.
    def event_key(events):
        return tuple(sorted(
            (
                event["room"],
                event["activity"],
                event["start_minute"],
                event["end_minute"],
            )
            for event in events
        ))

    config_path = ROOT / "data" / "config.json"

    training_config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    manifest["dataset_config_sha256"] = sha256(config_path)

    with (ROOT / "data" / "train.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        training_max_age = max(
            float(row["minutes_since_measurement"])
            for row in csv.DictReader(file)
        )

    manifest["training_max_measurement_age_minutes"] = (
        training_max_age
    )

    known_schedules = {
        event_key(item["scenario"]["events"])
        for item in training_config["scenarios"]
    }

    for day, late in SCENARIOS:
        proposed = [
            {
                "room": event.room,
                "activity": event.activity,
                "start_minute": event.start_minute,
                "end_minute": event.end_minute,
            }
            for event in generate_daily_events(
                EVENT_SEED,
                day,
                late_dinner=late,
            )
        ]

        if event_key(proposed) in known_schedules:
            raise ValueError(
                "An evaluation event schedule repeats the existing dataset."
            )

    manifest["event_schedules_disjoint_from_generated_data"] = True

    # Save the protocol before inspecting comparison results.
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    all_metrics = []
    all_rooms = []
    all_curves = []
    schedules = []

    # One home per policy: run the scenarios as consecutive days so that
    # forecasts can use previous-day measurements, as in the backend.
    first_day, first_late = SCENARIOS[0]
    options = {
        "seed": EVENT_SEED,
        "day_index": first_day,
        "late_dinner": first_late,
    }
    auto = Simulator(**options)
    patrol = Simulator(**options)
    policy = AutoModePolicy(predictor)

    for day, late in SCENARIOS:
        suffix = "late" if late else "normal"
        scenario_id = f"day_{day + 1:02d}_{suffix}"

        if day != first_day:
            auto.next_day(late_dinner=late)
            patrol.next_day(late_dinner=late)

        events = generate_daily_events(
            EVENT_SEED,
            day,
            late_dinner=late,
        )
        expected_events = [
            {
                "room": event.room,
                "activity": event.activity,
                "start_minute": event.start_minute,
                "end_minute": event.end_minute,
            }
            for event in events
        ]

        if auto.get_scenario()["events"] != expected_events:
            raise AssertionError(
                "The simulated day does not use the scenario schedule."
            )

        conditions_match = (
            auto.get_state() == patrol.get_state()
            and auto.get_map() == patrol.get_map()
            and auto.get_scenario() == patrol.get_scenario()
        )

        if not conditions_match:
            raise AssertionError(
                "Paired initial conditions do not match."
            )

        schedules.append({
            "scenario": scenario_id,
            "settings": auto.get_scenario(),
            "map": auto.get_map(),
        })

        for name, sim in [
            ("ai", auto),
            ("fixed_patrol", patrol),
        ]:
            before = dict(policy.counts)

            if name == "ai":
                tick = lambda: policy.tick(sim)
            else:
                tick = lambda: fixed_patrol_tick(sim)

            metrics, rooms, curves = evaluate_day(
                sim,
                tick,
                scenario_id,
                name,
            )

            # Fixed patrol makes neither kind of AI move.
            for key in ["forecast_moves", "stale_revisits"]:
                metrics[key] = (
                    policy.counts[key] - before[key]
                    if name == "ai" else 0
                )

            all_metrics.append(metrics)
            all_rooms.extend(rooms)
            all_curves.extend(curves)

        print(f"Completed {scenario_id}", flush=True)

    save_csv(output / "per_scenario.csv", all_metrics)
    save_csv(output / "per_room.csv", all_rooms)
    save_csv(output / "minute_records.csv", all_curves)

    (output / "scenarios.json").write_text(
        json.dumps(schedules, indent=2),
        encoding="utf-8",
    )

    metric_names = [
        key for key in all_metrics[0]
        if key not in ["scenario", "policy"]
    ]

    summary = []

    for name in ["ai", "fixed_patrol"]:
        group = [
            row for row in all_metrics
            if row["policy"] == name
        ]

        summary.append({
            "policy": name,
            **{
                key: statistics.mean(row[key] for row in group)
                for key in metric_names
            },
        })

    save_csv(output / "summary.csv", summary)

    paired = []

    scenario_ids = [
        row["scenario"] for row in all_metrics
        if row["policy"] == "ai"
    ]

    for scenario in scenario_ids:
        auto_row = next(
            row for row in all_metrics
            if row["scenario"] == scenario
            and row["policy"] == "ai"
        )

        fixed_row = next(
            row for row in all_metrics
            if row["scenario"] == scenario
            and row["policy"] == "fixed_patrol"
        )

        paired.append({
            "scenario": scenario,
            **{
                key + "_ai_minus_fixed":
                    auto_row[key] - fixed_row[key]
                for key in metric_names
            },
        })

    save_csv(output / "paired_differences.csv", paired)

    lines = [
        "# Paired Policy Evaluation",
        "",
        "Nine new synthetic scenarios: six normal and three late-dinner days.",
        "",
        "Values are means per scenario.",
        "",
        "| Metric | AI | Fixed patrol | AI minus fixed |",
        "| --- | ---: | ---: | ---: |",
    ]

    for key in metric_names:
        auto_value = summary[0][key]
        fixed_value = summary[1][key]

        lines.append(
            f"| {key} | {auto_value:.4f} | {fixed_value:.4f} "
            f"| {auto_value - fixed_value:.4f} |"
        )

    better = sum(
        row["room_minutes_above_threshold_ai_minus_fixed"] < 0
        for row in paired
    )

    worse = sum(
        row["room_minutes_above_threshold_ai_minus_fixed"] > 0
        for row in paired
    )

    tied = len(paired) - better - worse

    lines += [
        "",
        (
            f"Threshold room-minutes: AI better on {better}, "
            f"worse on {worse}, tied on {tied} scenarios."
        ),
        "",
        "Room-minutes sum durations across rooms and may exceed 1440.",
        "They do not represent human exposure without an occupancy model.",
        f"Excess PM minutes sum max(PM - {PURIFY_ON}, 0) using 1-minute samples.",
        "Travel distance is measured in actual grid cells.",
        (
            "Initial observations are identical, but startup patrol "
            "behavior differs as part of each policy."
        ),
        (
            f"Training measurement age is at most {training_max_age:g} "
            "minutes. Check operational ages before claiming reliability."
        ),
        (
            "Lower movement is not automatically better purification; "
            "observations may become stale."
        ),
        (
            "If policies are tuned using these results, use new scenarios "
            "for a fresh final evaluation."
        ),
        (
            "These are simulation results, not verified real-home "
            "performance or prediction MAE improvements."
        ),
    ]

    report = "\n".join(lines) + "\n"

    (output / "REPORT.md").write_text(
        report,
        encoding="utf-8",
    )

    print(report)
    print("Output directory:", output)


if __name__ == "__main__":
    main()