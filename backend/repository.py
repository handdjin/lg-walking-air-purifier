"""Persist shared simulation runs without user identity data."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.database import DB_PATH, connect_db, init_db


def utc_now():
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def encode(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )


class RunRecorder:
    def __init__(self, simulator, model_version, path=None):
        self.simulator = simulator
        self.path = Path(
            path or os.environ.get("AIR_PURIFIER_DB_PATH", DB_PATH)
        )
        self.run_id = str(uuid.uuid4())
        self.model_version = model_version

        self.cursor = 0
        self.event_sequence = 0
        self.decision_sequence = 0

        self.forecasts = {}
        self.decisions = {}
        self.status = "created"

        init_db(self.path)

        scenario = simulator.get_scenario()

        config = {
            "scenario": scenario,
            "map": simulator.get_map(),
            "scope": "shared simulation; no user identity",
        }

        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO simulation_runs("
                "run_id,status,policy_name,config_json,"
                "model_version,rule_version"
                ") VALUES (?, 'created', 'auto_manual', ?, ?, ?)",
                (
                    self.run_id,
                    encode(config),
                    model_version,
                    scenario.get("rule_version"),
                ),
            )

        self.sync(status="created")

    @staticmethod
    def recover_open_runs(path=None):
        """Single-worker startup: old live state is not restored."""
        path = Path(
            path or os.environ.get("AIR_PURIFIER_DB_PATH", DB_PATH)
        )

        init_db(path)

        with connect_db(path) as connection:
            connection.execute(
                "UPDATE simulation_runs "
                "SET status='interrupted', ended_at=? "
                "WHERE status IN ('created','running','paused')",
                (utc_now(),),
            )

    def sync(self, status=None, source="system"):
        """Save unseen events and advance cursors only after commit."""
        history = self.simulator.get_history()

        if len(history) < self.cursor:
            raise RuntimeError(
                "Simulator was reset without creating a new DB run."
            )

        state = self.simulator.get_state()

        if status is None:
            if state["finished"]:
                status = "completed"
            elif state["is_running"]:
                status = "running"
            else:
                status = "paused"

        if self.status in (
            "completed",
            "reset",
            "interrupted",
            "error",
        ):
            status = self.status

        pending = history[self.cursor:]

        if not pending and status == self.status:
            return

        with connect_db(self.path) as connection:
            for offset, event in enumerate(pending):
                physical = event["type"] in (
                    "measurement",
                    "arrival",
                    "purification_on",
                    "purification_off",
                    "day_finished",
                )

                event_source = "system" if physical else source

                connection.execute(
                    "INSERT INTO activity_events("
                    "run_id,event_sequence,time_seconds,event_type,"
                    "room_id,control_source,details_json"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (
                        self.run_id,
                        self.event_sequence + offset,
                        event["time_seconds"],
                        event["type"],
                        event.get("room") or event.get("destination"),
                        event_source,
                        encode(event),
                    ),
                )

                if event["type"] == "measurement":
                    connection.execute(
                        "INSERT INTO measurements("
                        "run_id,room_id,measured_at_seconds,"
                        "source_minute,pm25"
                        ") VALUES (?,?,?,?,?)",
                        (
                            self.run_id,
                            event["room"],
                            event["measured_at_seconds"],
                            event["source_minute"],
                            event["pm25"],
                        ),
                    )

            terminal = status in (
                "completed",
                "reset",
                "interrupted",
                "error",
            )

            connection.execute(
                "UPDATE simulation_runs SET status=?, "
                "started_at=CASE WHEN ?='running' "
                "THEN COALESCE(started_at,?) ELSE started_at END, "
                "ended_at=CASE WHEN ? "
                "THEN COALESCE(ended_at,?) ELSE ended_at END "
                "WHERE run_id=?",
                (
                    status,
                    status,
                    utc_now(),
                    terminal,
                    utc_now(),
                    self.run_id,
                ),
            )

        self.cursor = len(history)
        self.event_sequence += len(pending)
        self.status = status

    def save_forecast(self, forecast, observations):
        reference = int(forecast["reference_minute"] * 60)

        signature = encode({
            "forecast": forecast,
            "observations": observations,
        })

        if reference in self.forecasts:
            if self.forecasts[reference] != signature:
                raise RuntimeError(
                    "Conflicting forecasts at the same reference time."
                )
            return

        with connect_db(self.path) as connection:
            for room, value in forecast["predictions"].items():
                reading = observations.get(room) or {}
                measured = reading.get("measured_at_seconds")

                age = (
                    None
                    if measured is None
                    else reference - measured
                )

                connection.execute(
                    "INSERT INTO predictions("
                    "run_id,room_id,reference_seconds,target_seconds,"
                    "status,predicted_pm25,last_measured_pm25,"
                    "last_measured_at_seconds,observation_age_seconds,"
                    "model_version"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        self.run_id,
                        room,
                        reference,
                        int(forecast["target_minute"] * 60),
                        forecast["status"],
                        value,
                        reading.get("pm25"),
                        measured,
                        age,
                        self.model_version,
                    ),
                )

        self.forecasts[reference] = signature

    def save_decision(
        self,
        decision,
        source="automatic",
        key=None,
    ):
        signature = encode(decision)

        if key is not None and key in self.decisions:
            if self.decisions[key] != signature:
                raise RuntimeError(
                    "Conflicting decisions with the same key."
                )
            return

        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO decisions("
                "run_id,decision_sequence,decided_at_seconds,"
                "action,target_room,reason,control_source,details_json"
                ") VALUES (?,?,?,?,?,?,?,?)",
                (
                    self.run_id,
                    self.decision_sequence,
                    decision["decided_at_seconds"],
                    decision["action"],
                    decision["target_room"],
                    decision["reason"],
                    source,
                    signature,
                ),
            )

        self.decision_sequence += 1

        if key is not None:
            self.decisions[key] = signature

    def record_control(self, event_type, details):
        self.sync(source="manual")

        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO activity_events("
                "run_id,event_sequence,time_seconds,event_type,"
                "control_source,details_json"
                ") VALUES (?,?,?,?, 'manual', ?)",
                (
                    self.run_id,
                    self.event_sequence,
                    self.simulator.get_state()[
                        "simulation_time_seconds"
                    ],
                    event_type,
                    encode(details),
                ),
            )

        self.event_sequence += 1

    def finish(self, reason):
        if reason not in (
            "completed",
            "reset",
            "interrupted",
            "error",
        ):
            raise ValueError("Invalid run ending reason.")

        self.sync(status=reason)