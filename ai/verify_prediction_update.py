"""Run from the project root: python -m ai.verify_prediction_update."""

import asyncio
import contextlib
import io
import json
import math
from pathlib import Path

import backend.main as backend

from ai.integration_demo import prepare_scenario
from ai.predict import ROOMS, Predictor


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
                list(frame.columns) == predictor.input_columns,
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

        if seconds >= end_seconds:
            break

        sim.step()

    history = sim.get_history()

    measurements = [
        event for event in history
        if event["type"] == "measurement"
    ]

    for record in records:
        reference = record["reference_seconds"]
        for room in ROOMS:
            latest = max(
                (event["time_seconds"] for event in measurements
                 if event["room"] == room and event["time_seconds"] <= reference),
                default=None,
            )
            require(
                record["observations"][room]["measured_at_seconds"] == latest,
                f"{room}: forecast did not use the latest measurement.",
            )

    require(
        any(len({record["observations"][room]["measured_at_seconds"]
                 for record in records}) > 1 for room in ROOMS),
        "No refreshed readings were checked across forecasts.",
    )

    require(
        stale_room_proved,
        "No stale observation versus hidden-state case was checked.",
    )

    output = (
        Path(__file__).resolve().parent
        / "artifacts"
        / "uniform20_prediction_update_report.json"
    )

    output.parent.mkdir(exist_ok=True)

    report = {
        "result": "PASS",
        "scope": (
            "Controlled simulator/backend verification; "
            "not a real-phone or accuracy test"
        ),
        "checks": [
            "latest measured values",
            "fractional measurement age",
            "periodic measurement updates",
            "hidden-state exclusion",
            "status payload",
            "periodic replanning",
        ],
        "records": records,
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
        "PASS: periodic forecasts used refreshed readings."
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