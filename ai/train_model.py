FEATURES = [
    "room_id",
    "hour",
    "minute",
    "last_measured_pm25",
    "minutes_since_measurement",
]

LABEL = "target_pm25_30min"


# Model training, evaluation, and saving
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
    """Read a CSV and validate dates, inputs, and target times."""
    path = ROOT / "data" / f"{name}.csv"
    data = pd.read_csv(path)

    if data.empty:
        raise ValueError(f"{name}: No data found.")

    if not data["scenario_day"].between(first_day, last_day).all():
        raise ValueError(f"{name}: Dates are outside the expected range.")

    if not data["split"].eq(name).all():
        raise ValueError(f"{name}: Invalid split labels.")

    if set(data["room_id"]) != ROOMS:
        raise ValueError(f"{name}: Check the room names.")

    numeric = data[FEATURES[1:] + [LABEL]].to_numpy(dtype=float)

    if not np.isfinite(numeric).all() or (numeric < 0).any():
        raise ValueError(
            f"{name}: Missing, negative, or invalid numeric values."
        )

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
        raise ValueError(
            f"{name}: Invalid measurement or target times."
        )

    duplicate = data.duplicated(
        ["run_id", "scenario_day", "prediction_time", "room_id"]
    )

    if duplicate.any():
        raise ValueError(f"{name}: Duplicate samples found.")

    return data


def make_model(max_depth):
    """Combine room encoding and Random Forest in one pipeline."""
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

    # Compare two settings using validation data.
    for depth in [8, None]:
        model = make_model(depth)

        # Pass inputs and labels separately.
        model.fit(train[FEATURES], train[LABEL])

        prediction = model.predict(validation[FEATURES])

        error = mean_absolute_error(
            validation[LABEL],
            prediction,
        )

        candidates.append((error, depth, model))

        print(
            "Maximum depth:", depth,
            "/ Validation MAE:", round(error, 4),
        )

    # Select the model with the lowest validation error.
    validation_mae, depth, best_model = min(
        candidates,
        key=lambda item: item[0],
    )

    # Evaluate the test data after model selection.
    test = load_split("test", 52, 60)

    prediction = best_model.predict(test[FEATURES])

    test_mae = mean_absolute_error(
        test[LABEL],
        prediction,
    )

    # Baseline: use the latest measurement as the future prediction.
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

    # Save preprocessing and the model together.
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

    print("\nTraining and evaluation complete")
    print("Test MAE:", round(test_mae, 4))
    print("Baseline MAE:", round(baseline_mae, 4))
    print("MAE by room:", room_mae)
    print("Output directory:", output)


if __name__ == "__main__":
    main()
