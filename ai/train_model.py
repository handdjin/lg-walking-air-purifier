FEATURES = [
    "room_id",
    "hour",
    "minute",
    "last_measured_pm25",
    "minutes_since_measurement",
]

LABEL = "target_pm25_30min"


# 모델 학습·평가·저장 파트
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


ROOT = Path(__file__).resolve().parent

FEATURES = [
    "room_id",
    "hour",
    "minute",
    "last_measured_pm25",
    "minutes_since_measurement",
]

LABEL = "target_pm25_30min"

ROOMS = {"living_room", "kitchen", "bedroom"}


def load_split(name, first_day, last_day):
    """CSV를 읽고 날짜·입력·정답 시각을 검사합니다."""
    path = ROOT / "data" / f"{name}.csv"
    data = pd.read_csv(path)

    if data.empty:
        raise ValueError(f"{name}: 자료가 없습니다.")

    if not data["scenario_day"].between(first_day, last_day).all():
        raise ValueError(f"{name}: 잘못된 날짜가 포함되어 있습니다.")

    if not data["split"].eq(name).all():
        raise ValueError(f"{name}: split 구분이 잘못되었습니다.")

    if set(data["room_id"]) != ROOMS:
        raise ValueError(f"{name}: 방 이름을 확인하세요.")

    numeric = data[FEATURES[1:] + [LABEL]].to_numpy(dtype=float)

    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError(f"{name}: 결측·음수·잘못된 숫자가 있습니다.")

    reference = (
        pd.to_timedelta(data["prediction_time"] + ":00")
        .dt.total_seconds() / 60
    )

    target = (
        pd.to_timedelta(data["target_time"] + ":00")
        .dt.total_seconds() / 60
    )

    measured = (
        pd.to_timedelta(data["last_measured_at"] + ":00")
        .dt.total_seconds() / 60
    )

    valid_times = (
        (target - reference == 30)
        & (measured <= reference)
        & (
            reference - measured
            == data["minutes_since_measurement"]
        )
        & (data["hour"] * 60 + data["minute"] == reference)
        & (target < 1440)
    )

    if not valid_times.all():
        raise ValueError(f"{name}: 측정 시각 또는 정답 시각이 잘못되었습니다.")

    duplicate = data.duplicated(
        ["run_id", "scenario_day", "prediction_time", "room_id"]
    )

    if duplicate.any():
        raise ValueError(f"{name}: 중복된 사례가 있습니다.")

    return data


def make_model(max_depth):
    """방 이름 변환과 Random Forest를 하나로 묶습니다."""
    preprocessing = ColumnTransformer([
        (
            "room",
            OneHotEncoder(
                handle_unknown="error",
                sparse_output=False,
            ),
            ["room_id"],
        ),
        (
            "numbers",
            "passthrough",
            FEATURES[1:],
        ),
    ])

    return Pipeline([
        ("preprocessing", preprocessing),
        (
            "model",
            RandomForestRegressor(
                n_estimators=120,
                max_depth=max_depth,
                min_samples_leaf=3,
                random_state=42,
                n_jobs=-1,
            ),
        ),
    ])


def main():
    train = load_split("train", 1, 42)
    validation = load_split("validation", 43, 51)

    candidates = []

    # 검증 자료로 두 설정을 비교합니다.
    for depth in [8, None]:
        model = make_model(depth)

        # 입력과 정답을 별도로 전달합니다.
        model.fit(train[FEATURES], train[LABEL])

        prediction = model.predict(validation[FEATURES])

        error = mean_absolute_error(
            validation[LABEL],
            prediction,
        )

        candidates.append((error, depth, model))

        print(
            "최대 깊이:", depth,
            "/ 검증 MAE:", round(error, 4),
        )

    # 검증 오차가 가장 작은 모델 선택
    validation_mae, depth, best_model = min(
        candidates,
        key=lambda item: item[0],
    )

    # 모델 선택 후 시험 자료를 평가합니다.
    test = load_split("test", 52, 60)

    prediction = best_model.predict(test[FEATURES])

    test_mae = mean_absolute_error(
        test[LABEL],
        prediction,
    )

    # 비교 기준: 마지막 측정값을 미래 예측값으로 그대로 사용
    baseline_mae = mean_absolute_error(
        test[LABEL],
        test["last_measured_pm25"],
    )

    results = test.copy()
    results["predicted_pm25"] = prediction

    room_mae = {
        room: float(
            mean_absolute_error(
                group[LABEL],
                group["predicted_pm25"],
            )
        )
        for room, group in results.groupby("room_id")
    }

    pattern_mae = {
        pattern: float(
            mean_absolute_error(
                group[LABEL],
                group["predicted_pm25"],
            )
        )
        for pattern, group in results.groupby("patrol_pattern")
    }

    report = {
        "sklearn_version": sklearn.__version__,
        "features": FEATURES,
        "label": LABEL,
        "selected_max_depth": depth,
        "validation_mae": float(validation_mae),
        "test_mae": float(test_mae),
        "baseline_test_mae": float(baseline_mae),
        "per_room_mae": room_mae,
        "per_pattern_mae": pattern_mae,
        "rows": {
            "train": len(train),
            "validation": len(validation),
            "test": len(test),
        },
    }

    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)

    # 입력 변환과 모델을 함께 저장합니다.
    joblib.dump(
        best_model,
        output / "pm25_model.joblib",
    )

    results.to_csv(
        output / "test_predictions.csv",
        index=False,
    )

    (output / "metrics.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("\n학습·평가 완료")
    print("시험 MAE:", round(test_mae, 4))
    print("기준선 MAE:", round(baseline_mae, 4))
    print("방별 MAE:", room_mae)
    print("저장 위치:", output)


if __name__ == "__main__":
    main()