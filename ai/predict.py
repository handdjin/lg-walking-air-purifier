# 예측함수

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
        같은 현재 시각에서 세 방의 30분 뒤 농도를 예측합니다.

        observations 예시:
        {
            "kitchen": {
                "pm25": 31,
                "measured_minute": 550
            }
        }
        """
        if type(now_minute) is not int or not 0 <= now_minute < 1440:
            raise ValueError("현재 시각은 0~1439 사이의 정수여야 합니다.")

        if not isinstance(observations, dict):
            raise ValueError("측정 기록은 딕셔너리여야 합니다.")

        if set(observations) - set(ROOMS):
            raise ValueError("알 수 없는 방 이름이 있습니다.")

        missing = False
        rows = []

        for room in ROOMS:
            reading = observations.get(room)

            if reading is None:
                missing = True
                continue

            if not isinstance(reading, dict):
                raise ValueError(f"{room}: 측정 기록 형식이 잘못되었습니다.")

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
                raise ValueError(f"{room}: 측정값 또는 시각을 확인하세요.")

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