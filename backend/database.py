"""SQLite schema setup. Run: python -m backend.database [--verify]."""

import argparse
import json
import sqlite3
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "data" / "app.db"

TABLES = (
    "simulation_runs",
    "measurements",
    "predictions",
    "decisions",
    "activity_events",
)

SCHEMA_VERSION = 1


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
    UNIQUE (run_id, room_id, measured_at_seconds)
);

CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
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
    UNIQUE (run_id, room_id, reference_seconds)
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
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
    UNIQUE (run_id, decision_sequence)
);

CREATE TABLE IF NOT EXISTS activity_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL
        REFERENCES simulation_runs(run_id) ON DELETE RESTRICT,
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
    UNIQUE (run_id, event_sequence)
);

CREATE INDEX IF NOT EXISTS idx_measurements_run_time
    ON measurements(run_id, measured_at_seconds);

CREATE INDEX IF NOT EXISTS idx_predictions_run_time
    ON predictions(run_id, reference_seconds);

CREATE INDEX IF NOT EXISTS idx_decisions_run_time
    ON decisions(run_id, decided_at_seconds);

CREATE INDEX IF NOT EXISTS idx_events_run_time
    ON activity_events(run_id, time_seconds);
"""


@contextmanager
def connect_db(path=DB_PATH):
    """Commit on success, roll back on error, and always close."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, timeout=5)

    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")

        with connection:
            yield connection

    finally:
        connection.close()


def init_db(path=DB_PATH):
    """Create missing tables without clearing existing records."""
    with connect_db(path) as connection:
        version = connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]

        existing = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        if (
            version not in (0, SCHEMA_VERSION)
            or (version == 0 and existing)
        ):
            raise RuntimeError(
                "Existing schema needs inspection or a migration; "
                "nothing was replaced."
            )

        connection.execute("PRAGMA journal_mode = WAL")

        connection.executescript(
            "BEGIN IMMEDIATE;\n"
            + SCHEMA
            + f"\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;"
        )


def table_counts(path=DB_PATH):
    with connect_db(path) as connection:
        return {
            name: connection.execute(
                f"SELECT COUNT(*) FROM {name}"
            ).fetchone()[0]
            for name in TABLES
        }


def verify_setup():
    """Use a temporary DB; do not insert sample data into app.db."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "check.db"

        init_db(path)
        run_id = str(uuid.uuid4())

        with connect_db(path) as connection:
            connection.execute(
                "INSERT INTO simulation_runs(run_id, config_json) "
                "VALUES (?, ?)",
                (
                    run_id,
                    json.dumps({"purpose": "schema_verification"}),
                ),
            )

            connection.execute(
                "INSERT INTO measurements("
                "run_id,room_id,measured_at_seconds,source_minute,pm25"
                ") VALUES (?, 'kitchen', 100, 1, 12.97)",
                (run_id,),
            )

            connection.execute(
                "INSERT INTO predictions("
                "run_id,room_id,reference_seconds,target_seconds,status,"
                "predicted_pm25,last_measured_pm25,"
                "last_measured_at_seconds,observation_age_seconds"
                ") VALUES (?, 'kitchen', 600, 2400, 'ok', "
                "40, 12.97, 100, 500)",
                (run_id,),
            )

            connection.execute(
                "INSERT INTO decisions("
                "run_id,decision_sequence,decided_at_seconds,"
                "action,target_room,reason"
                ") VALUES (?, 0, 600, 'move', 'kitchen', 'highest_score')",
                (run_id,),
            )

            connection.execute(
                "INSERT INTO activity_events("
                "run_id,event_sequence,time_seconds,event_type,room_id"
                ") VALUES (?, 0, 600, 'move_requested', 'kitchen')",
                (run_id,),
            )

        expected = dict.fromkeys(TABLES, 1)

        if table_counts(path) != expected:
            raise AssertionError("Save/read verification failed.")

        init_db(path)

        if table_counts(path) != expected:
            raise AssertionError(
                "Repeated initialization changed existing records."
            )

        invalid_statements = [
            (
                "INSERT INTO measurements("
                "run_id,room_id,measured_at_seconds,pm25"
                ") VALUES ('missing-run','kitchen',200,10)",
                (),
            ),
            (
                "INSERT INTO measurements("
                "run_id,room_id,measured_at_seconds,pm25"
                ") VALUES (?, 'kitchen',100,10)",
                (run_id,),
            ),
            (
                "INSERT INTO predictions("
                "run_id,room_id,reference_seconds,target_seconds,status"
                ") VALUES (?, 'kitchen',1200,3000,'ok')",
                (run_id,),
            ),
            (
                "DELETE FROM simulation_runs WHERE run_id=?",
                (run_id,),
            ),
        ]

        for statement, parameters in invalid_statements:
            try:
                with connect_db(path) as connection:
                    connection.execute(statement, parameters)

            except sqlite3.IntegrityError:
                pass

            else:
                raise AssertionError(
                    "An invalid record was accepted."
                )

        if table_counts(path) != expected:
            raise AssertionError(
                "Integrity checks changed saved records."
            )

    print(
        "PASS: save/read, repeat initialization, "
        "foreign keys, duplicates, and constraints"
    )
    print(
        "Temporary verification data removed; "
        "app.db was not changed by this check."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()

    if args.verify:
        verify_setup()
        return

    init_db()

    print("Database ready:", DB_PATH)

    for name, count in table_counts().items():
        print(f"{name}: {count} rows")


if __name__ == "__main__":
    main()