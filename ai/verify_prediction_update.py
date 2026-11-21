"""Run from the project root: python -m ai.verify_prediction_update."""

import asyncio
import contextlib
import io
import json
import math
from pathlib import Path

import backend.main as backend

from ai.integration_demo import prepare_scenario
from ai.predict import FEATURES, ROOMS, Predictor


def require(condition, message):
    """Stop verification if a condition is not satisfied."""
    if not condition:
        raise AssertionError(message)


class RecordingModel:
    """Record real model inputs without changing predictions."""

    def __init__(self, model):
        self.model = model
        self.inputs = None

    def predict(self, inputs):
        self.inputs = inputs.copy()
        return self.model.predict(inputs)


def main():
    # Use actual simulated measurements from the existing demo scenario.
    sim = prepare_scenario(early_breakfast=False)

    predictor = Predictor()
    recorder = RecordingModel(predictor.model)
    predictor.model = recorder

    # Only this verifier may read ground truth for evaluation.
    evaluation_truth = sim.get_ground_truth

    def forbidden_truth():
        raise AssertionError(
            "Prediction or status attempted a ground-truth lookup."
        )

    sim.get_ground_truth = forbidden_truth

    # Use this process's simulator, not the running server's simulator.
    backend.simulator = sim
    backend.predictor = predictor
    backend.latest_prediction = None
    backend.latest_decision = None
    backend.last_prediction_seconds = None

    records = []
    purification_values = []
    stale_room_proved = False

    # Finish after the 09:40 prediction.
    end_seconds = 580 * 60

    while True:
        before = sim.get_state()
        seconds = before["simulation_time_seconds"]
        previous_forecast = backend.last_prediction_seconds

        # Execute the same operations as the server loop.
        with contextlib.redirect_stdout(io.StringIO()):
            backend.initial_patrol()
            backend.auto_decision()

        if backend.last_prediction_seconds != previous_forecast:
            forecast = backend.latest_prediction

            require(
                forecast["status"] == "ok",
                "Forecast is not ready.",
            )

            frame = recorder.inputs

            require(
                frame is not None,
                "The model was not called.",
            )

            require(
                list(frame.columns) == FEATURES,
                "Unexpected model input columns.",
            )

            require(
                set(frame["room_id"]) == set(ROOMS),
                "Missing room inputs.",
            )

            inputs = frame.set_index("room_id")

            # Evaluation-only values are never passed to the model.
            actual = evaluation_truth()["pm25"]

            for room in ROOMS:
                reading = before["observations"][room]
                row = inputs.loc[room]

                expected_age = (
                    seconds - reading["measured_at_seconds"]
                ) / 60

                require(
                    math.isclose(
                        row["last_measured_pm25"],
                        reading["pm25"],
                    ),
                    f"{room}: latest measurement was not used.",
                )

                require(
                    math.isclose(
                        row["minutes_since_measurement"],
                        expected_age,
                    ),
                    f"{room}: incorrect measurement age.",
                )

                require(
                    row["hour"] == seconds // 3600
                    and row["minute"] == seconds % 3600 // 60,
                    f"{room}: incorrect reference time.",
                )

                if (
                    room != before["current_room"]
                    and not math.isclose(
                        actual[room],
                        reading["pm25"],
                    )
                ):
                    stale_room_proved = True

            # Verify the status payload used by the app.
            payload = asyncio.run(backend.get_status())

            require(
                payload["observations"]
                == sim.get_state()["observations"],
                "Status observations were changed.",
            )

            require(
                payload["ai_prediction"] == forecast,
                "Status forecast is stale.",
            )

            require(
                payload["ai_decision"]
                == backend.latest_decision,
                "Status decision is inconsistent.",
            )

            require(
                "ground_truth" not in payload
                and "true_pm25" not in payload,
                "Hidden ground truth is exposed in status.",
            )

            records.append({
                "reference_seconds": seconds,
                "model_inputs": frame.to_dict(orient="records"),
                "observations": before["observations"],
                "forecast": forecast,
                "decision": backend.latest_decision,
            })

        state = sim.get_state()

        # Ground truth is inspected here only to verify gradual removal.
        if state["is_purifying"] and seconds % 60 == 0:
            purification_values.append({
                "time_seconds": seconds,
                "pm25": evaluation_truth()["pm25"]["kitchen"],
            })

        if seconds >= end_seconds:
            break

        sim.step()

    history = sim.get_history()

    measurements = [
        event for event in history
        if event["type"] == "measurement"
    ]

    arrivals = [
        event for event in history
        if event["type"] == "arrival"
        and event["time_seconds"] > 31200
    ]

    starts = [
        event for event in history
        if event["type"] == "purification_on"
        and event["time_seconds"] > 31200
    ]

    stops = [
        event for event in history
        if event["type"] == "purification_off"
        and event["time_seconds"] > 31200
    ]

    require(
        arrivals and arrivals[0]["room"] == "kitchen",
        "No predicted kitchen arrival.",
    )

    arrival = arrivals[0]

    require(
        any(
            event["room"] == "kitchen"
            and event["time_seconds"] == arrival["time_seconds"]
            for event in measurements
        ),
        "No immediate arrival measurement.",
    )

    require(
        starts and stops,
        "Purification did not start and stop.",
    )

    require(
        starts[0]["time_seconds"] > arrival["time_seconds"],
        "This scenario should wait for pollution after arrival.",
    )

    require(
        len(purification_values) >= 2
        and purification_values[-1]["pm25"]
        < purification_values[0]["pm25"]
        and purification_values[0]["pm25"] > 5,
        "Gradual purification was not observed.",
    )

    by_time = {
        record["reference_seconds"]: record
        for record in records
    }

    require(
        31800 in by_time
        and 33600 in by_time
        and 34800 in by_time,
        "Expected forecasts are missing.",
    )

    require(
        by_time[31800]["observations"]["kitchen"][
            "measured_at_seconds"
        ] == 31300,
        "The next forecast did not use the arrival observation.",
    )

    require(
        by_time[33600]["observations"]["kitchen"][
            "measured_at_seconds"
        ] == 33100,
        "The next forecast did not use the periodic observation.",
    )

    require(
        stale_room_proved,
        "No stale observation versus hidden-state case was checked.",
    )

    output = (
        Path(__file__).resolve().parent
        / "artifacts"
        / "prediction_update_report.json"
    )

    output.parent.mkdir(exist_ok=True)

    report = {
        "result": "PASS",
        "scope": (
            "Controlled simulator/backend verification; "
            "not a real-phone or accuracy test"
        ),
        "checks": [
            "arrival measurement",
            "latest measured values",
            "fractional measurement age",
            "periodic measurement updates",
            "hidden-state exclusion",
            "status payload",
            "gradual purification",
            "periodic replanning",
        ],
        "records": records,
        "purification_evaluation_only": purification_values,
        "events": [
            event for event in history
            if event["time_seconds"] >= 31200
        ],
    }

    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("PASS: new observations are used by subsequent forecasts.")
    print("PASS: measurement ages use actual seconds / 60.")
    print("PASS: hidden room states are not used as measurements.")
    print(
        "PASS: arrival, waiting, purification, "
        "and periodic replanning completed."
    )

    for record in records:
        kitchen = next(
            row for row in record["model_inputs"]
            if row["room_id"] == "kitchen"
        )

        print(
            f"minute={record['reference_seconds'] // 60}, "
            f"last_pm25={kitchen['last_measured_pm25']:.2f}, "
            f"age_minutes={kitchen['minutes_since_measurement']:.2f}"
        )

    print("Report:", output)


if __name__ == "__main__":
    main()