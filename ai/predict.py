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


class Predictor:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = (
                Path(__file__).resolve().parent
                / "artifacts"
                / "pm25_model.joblib"
            )

        self.model = joblib.load(model_path)

    def predict_rooms(self, now_minute, observations):
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
                type(measured) is int
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

        if missing:
            status = "initial_patrol_required"
        elif now_minute + 30 >= 1440:
            status = "cross_day_horizon_not_supported"
        else:
            status = "ok"

        values = [None, None, None]

        if status == "ok":
            inputs = pd.DataFrame(rows, columns=FEATURES)
            values = self.model.predict(inputs).tolist()

        return {
            "reference_minute": now_minute,
            "target_minute": now_minute + 30,
            "status": status,
            "predictions": dict(zip(ROOMS, values)),
        }


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
