# Prediction function

import json
import math
from pathlib import Path

import joblib
import pandas as pd


ROOMS = ["living_room", "kitchen", "bedroom"]

FEATURES = [
    "room_id",
    "hour",
    "minute",
    "last_measured_pm25",
    "minutes_since_measurement",
]


HISTORY_FEATURES = ["days_observed", "historical_mean", "polluted_day_ratio"]


def recent_features(previous_days, room, target_minute):
    peaks = []
    for readings in previous_days:
        values = [pm for second, pm in readings[room]
                  if abs(second - target_minute * 60) <= 900]
        if values:
            peaks.append(max(values))
    if not peaks:
        return [0, -1, -1]
    return [len(peaks), sum(peaks) / len(peaks),
            sum(value >= 20 for value in peaks) / len(peaks)]


class Predictor:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "artifacts"
                / "uniform20_model.joblib"
            )

        self.model = joblib.load(model_path)
        self.input_columns = list(self.model.feature_names_in_)
        if self.input_columns not in (FEATURES, FEATURES + HISTORY_FEATURES):
            raise ValueError("Unexpected PM2.5 model input columns")
        self.model.steps[-1][1].n_jobs = 1

    def predict_rooms(self, now_minute, observations, previous_days=()):
        """
        Predict concentrations 30 minutes ahead for all three rooms
        using the same reference time.

        Example observations:
        {
            "kitchen": {
                "pm25": 31,
                "measured_minute": 550
            }
        }
        """
        if type(now_minute) is not int or not 0 <= now_minute < 1440:
            raise ValueError(
                "The current time must be an integer between 0 and 1439."
            )

        if not isinstance(observations, dict):
            raise ValueError("Observations must be a dictionary.")

        if set(observations) - set(ROOMS):
            raise ValueError("Unknown room names are present.")

        missing = False
        rows = []

        for room in ROOMS:
            reading = observations.get(room)

            if reading is None:
                missing = True
                continue

            if not isinstance(reading, dict):
                raise ValueError(f"{room}: Invalid observation format.")

            value = reading.get("pm25")
            measured = reading.get("measured_minute")

            if value is None or measured is None:
                missing = True
                continue

            valid_value = (
                not isinstance(value, bool)
                and isinstance(value, (int, float))
                and math.isfinite(value)
                and value >= 0
            )

            valid_time = (
                not isinstance(measured, bool)
                and isinstance(measured, (int, float))
                and math.isfinite(measured)
                and 0 <= measured <= now_minute
                )

            if not valid_value or not valid_time:
                raise ValueError(
                    f"{room}: Check the measurement value or time."
                )

            rows.append([
                room,
                now_minute // 60,
                now_minute % 60,
                value,
                now_minute - measured,
            ])
            if self.input_columns == FEATURES + HISTORY_FEATURES:
                rows[-1].extend(recent_features(previous_days, room, now_minute + 30))

        if missing:
            status = "initial_patrol_required"
        elif now_minute + 30 >= 1440:
            status = "cross_day_horizon_not_supported"
        else:
            status = "ok"

        values = [None, None, None]

        if status == "ok":
            inputs = pd.DataFrame(rows, columns=self.input_columns)
            values = self.model.predict(inputs).tolist()

        return {
            "reference_minute": now_minute,
            "target_minute": now_minute + 30,
            "status": status,
            "predictions": dict(zip(ROOMS, values)),
        }


def predict_from_simulator(predictor, simulator):
    """Convert simulator observations and request a forecast."""
    state = simulator.get_state()
    seconds = state["simulation_time_seconds"]

    if state["finished"]:
        return {
            "status": "simulation_finished",
            "predictions": dict.fromkeys(ROOMS),
        }

    # Request forecasts at 10-minute boundaries.
    if seconds % 600 != 0:
        return {
            "status": "not_prediction_time",
            "predictions": dict.fromkeys(ROOMS),
        }

    observations = {}

    for room in ROOMS:
        reading = state["observations"].get(room)

        if (
            reading is None
            or reading["pm25"] is None
            or reading["measured_at_seconds"] is None
        ):
            observations[room] = None
        else:
            observations[room] = {
                "pm25": reading["pm25"],
                "measured_minute":
                    reading["measured_at_seconds"] / 60,
            }

    return predictor.predict_rooms(
        now_minute=seconds // 60,
        observations=observations,
        previous_days=simulator.previous_days,
    )


if __name__ == "__main__":
    predictor = Predictor()

    result = predictor.predict_rooms(
        now_minute=560,
        observations={
            "living_room": {
                "pm25": 12,
                "measured_minute": 540,
            },
            "kitchen": {
                "pm25": 31,
                "measured_minute": 550,
            },
            "bedroom": {
                "pm25": 18,
                "measured_minute": 560,
            },
        },
    )

    print(json.dumps(result, indent=2))
