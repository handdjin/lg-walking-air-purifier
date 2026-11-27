"""SQLite schema version 2, with lossless migration from version 1."""

import argparse
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"
TABLES = ("simulation_runs", "measurements", "predictions", "decisions", "activity_events")
SCHEMA_VERSION = 2


def database_path(path=None):
    return Path(path or os.environ.get("AIR_PURIFIER_DB_PATH", DB_PATH))


SCHEMA = """

CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    status TEXT NOT NULL DEFAULT 'created'
        CHECK (status IN (
            'created','running','paused','completed',
            'reset','interrupted','error'
        )),
    policy_name TEXT NOT NULL DEFAULT 'ai',
    config_json TEXT NOT NULL DEFAULT '{}',
    model_version TEXT,
    rule_version TEXT,
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),
    started_at TEXT,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS measurements (
    measurement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
    simulation_day INTEGER NOT NULL DEFAULT 1
        CHECK (typeof(simulation_day)='integer' AND simulation_day >= 1),
    room_id TEXT NOT NULL
        CHECK (room_id IN ('living_room','kitchen','bedroom')),
    measured_at_seconds INTEGER NOT NULL
        CHECK (
            typeof(measured_at_seconds)='integer'
            AND measured_at_seconds >= 0
        ),
    source_minute INTEGER
        CHECK (
            source_minute >= 0
            AND source_minute*60 <= measured_at_seconds
        ),
    pm25 REAL NOT NULL
        CHECK (pm25 >= 0 AND pm25 <= 1.7976931348623157e308),
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),
    UNIQUE (run_id, simulation_day, room_id, measured_at_seconds)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
    simulation_day INTEGER NOT NULL DEFAULT 1
        CHECK (typeof(simulation_day)='integer' AND simulation_day >= 1),
    room_id TEXT NOT NULL
        CHECK (room_id IN ('living_room','kitchen','bedroom')),
    reference_seconds INTEGER NOT NULL
        CHECK (
            typeof(reference_seconds)='integer'
            AND reference_seconds >= 0
        ),
    target_seconds INTEGER NOT NULL
        CHECK (target_seconds = reference_seconds + 1800),
    status TEXT NOT NULL
        CHECK (status IN (
            'ok',
            'initial_patrol_required',
            'cross_day_horizon_not_supported',
            'simulation_finished',
            'not_prediction_time',
            'error'
        )),
    predicted_pm25 REAL
        CHECK (
            predicted_pm25 >= 0
            AND predicted_pm25 <= 1.7976931348623157e308
        ),
    last_measured_pm25 REAL
        CHECK (last_measured_pm25 >= 0),
    last_measured_at_seconds INTEGER
        CHECK (
            last_measured_at_seconds >= 0
            AND last_measured_at_seconds <= reference_seconds
        ),
    observation_age_seconds INTEGER
        CHECK (observation_age_seconds >= 0),
    model_version TEXT,
    input_features_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),
    CHECK (
        (status='ok' AND predicted_pm25 IS NOT NULL)
        OR (status<>'ok' AND predicted_pm25 IS NULL)
    ),
    CHECK (
        (
            last_measured_at_seconds IS NULL
            AND observation_age_seconds IS NULL
        )
        OR (
            last_measured_at_seconds IS NOT NULL
            AND observation_age_seconds IS NOT NULL
            AND observation_age_seconds
                = reference_seconds-last_measured_at_seconds
        )
    ),
    UNIQUE (run_id, simulation_day, room_id, reference_seconds)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
    simulation_day INTEGER NOT NULL DEFAULT 1
        CHECK (typeof(simulation_day)='integer' AND simulation_day >= 1),
    decision_sequence INTEGER NOT NULL
        CHECK (decision_sequence >= 0),
    decided_at_seconds INTEGER NOT NULL
        CHECK (decided_at_seconds >= 0),
    action TEXT NOT NULL
        CHECK (action IN ('move','stay','wait')),
    target_room TEXT
        CHECK (target_room IN ('living_room','kitchen','bedroom')),
    reason TEXT NOT NULL,
    control_source TEXT NOT NULL DEFAULT 'automatic'
        CHECK (control_source IN ('automatic','manual','system')),
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),
    CHECK (
        (action='wait' AND target_room IS NULL)
        OR (
            action IN ('move','stay')
            AND target_room IS NOT NULL
        )
    ),
    UNIQUE (run_id, simulation_day, decision_sequence)
);

CREATE TABLE IF NOT EXISTS activity_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
    simulation_day INTEGER NOT NULL DEFAULT 1
        CHECK (typeof(simulation_day)='integer' AND simulation_day >= 1),
    event_sequence INTEGER NOT NULL
        CHECK (event_sequence >= 0),
    time_seconds INTEGER NOT NULL
        CHECK (time_seconds >= 0),
    event_type TEXT NOT NULL,
    room_id TEXT
        CHECK (room_id IN ('living_room','kitchen','bedroom')),
    control_source TEXT NOT NULL DEFAULT 'system'
        CHECK (control_source IN ('automatic','manual','system')),
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (
        strftime('%Y-%m-%dT%H:%M:%fZ','now')
    ),
    UNIQUE (run_id, simulation_day, event_sequence)
);

CREATE INDEX IF NOT EXISTS idx_measurements_run_time
    ON measurements(run_id, simulation_day, measured_at_seconds);

CREATE INDEX IF NOT EXISTS idx_predictions_run_time
    ON predictions(run_id, simulation_day, reference_seconds);

CREATE INDEX IF NOT EXISTS idx_decisions_run_time
    ON decisions(run_id, simulation_day, decided_at_seconds);

CREATE INDEX IF NOT EXISTS idx_events_run_time
    ON activity_events(run_id, simulation_day, time_seconds);
"""


@contextmanager
def connect_db(path=None):
    path = database_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        with connection:
            yield connection
    finally:
        connection.close()


def statements():
    return [part.strip() for part in SCHEMA.split(";") if part.strip()]


def init_db(path=None):
    """Create v2 or back up and atomically migrate v1; never erase history."""
    path = database_path(path)
    with connect_db(path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if version not in (0, 1, 2) or (version == 0 and tables):
            raise RuntimeError("Unknown database schema; no tables were replaced.")
        if version in (1, 2) and tables != set(TABLES):
            raise RuntimeError("Unexpected tables; inspect the DB before migration.")
        if version == 2:
            for table in TABLES[1:]:
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "simulation_day" not in columns:
                    raise RuntimeError("Version 2 is missing simulation_day.")
            return
        connection.execute("PRAGMA journal_mode=WAL")
        if version == 1:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
            backup = path.with_name(f"{path.stem}.before_v2_{stamp}.db")
            with sqlite3.connect(backup) as target:
                connection.backup(target)
            print("Schema v1 backup:", backup)

        connection.execute("BEGIN IMMEDIATE")
        if version == 1:
            for table in TABLES[1:]:
                statement = next(s for s in statements()
                                 if s.startswith(f"CREATE TABLE IF NOT EXISTS {table} ("))
                temporary = table + "_v2"
                connection.execute(statement.replace(
                    f"CREATE TABLE IF NOT EXISTS {table} (", f"CREATE TABLE {temporary} (", 1))
                columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
                names = ",".join(columns)
                connection.execute(f"INSERT INTO {temporary} ({names}) SELECT {names} FROM {table}")
                connection.execute(f"DROP TABLE {table}")
                connection.execute(f"ALTER TABLE {temporary} RENAME TO {table}")
            # Old records were single-day; default simulation_day is 1.
        for statement in statements():
            connection.execute(statement)
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign-key check failed; migration was rolled back.")


def table_counts(path=None):
    with connect_db(path) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in TABLES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        from backend.verify_persistence import verify_schema
        verify_schema()
        return
    init_db()
    print("Database ready:", database_path())
    print("Schema version:", SCHEMA_VERSION)
    for name, count in table_counts().items():
        print(f"{name}: {count} rows")


if __name__ == "__main__":
    main()
