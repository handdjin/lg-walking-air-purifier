"""Read local history: python -m backend.show_records [--day 3] [--run UUID]."""

import argparse
import json
import sqlite3

from backend.database import database_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day", type=int)
    parser.add_argument("--run")
    args = parser.parse_args()
    if args.day is not None and args.day < 1:
        parser.error("day must be at least 1")
    path = database_path().resolve()
    if not path.exists():
        raise SystemExit("Database not found. Run python -m backend.database first.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        if connection.execute("PRAGMA user_version").fetchone()[0] != 2:
            raise SystemExit("Run python -m backend.database to back up and migrate schema v1.")
        runs = [dict(row) for row in connection.execute(
            "SELECT run_id,status,created_at,started_at,ended_at "
            "FROM simulation_runs ORDER BY rowid DESC LIMIT 5")]
        print("Recent runs:")
        print(json.dumps(runs, indent=2))
        if not runs:
            print("No simulation runs saved yet.")
            return
        run_id = args.run or runs[0]["run_id"]
        counts = [dict(row) for row in connection.execute(
            "SELECT simulation_day,COUNT(*) AS measurements FROM measurements "
            "WHERE run_id=? GROUP BY simulation_day ORDER BY simulation_day", (run_id,))]
        day = args.day or (counts[-1]["simulation_day"] if counts else 1)
        print("Selected run:", run_id)
        print("Measurements by simulation day:")
        print(json.dumps(counts, indent=2))
        print("Selected simulation day:", day)
        for table, key in (("measurements", "measurement_id"), ("predictions", "prediction_id"),
                           ("decisions", "decision_id"), ("activity_events", "event_id")):
            total = connection.execute(
                f"SELECT COUNT(*) FROM {table} WHERE run_id=? AND simulation_day=?", (run_id, day)).fetchone()[0]
            rows = [dict(row) for row in connection.execute(
                f"SELECT * FROM {table} WHERE run_id=? AND simulation_day=? ORDER BY {key} DESC LIMIT 3",
                (run_id, day))]
            for row in rows:
                if "input_features_json" in row:
                    row["input_features"] = json.loads(row.pop("input_features_json"))
            print(f"{table}: {total} rows; latest 3:")
            print(json.dumps(rows, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
