"""Save shared multiday simulation history and read past observations."""

import json
import uuid
from datetime import datetime, timezone

from backend.database import connect_db, database_path, init_db

ROOMS = ("living_room", "kitchen", "bedroom")
TERMINAL = ("completed", "reset", "interrupted", "error")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class RunRecorder:
    def __init__(self, simulator, model_version, path=None):
        self.simulator = simulator
        self.path = database_path(path)
        self.run_id = str(uuid.uuid4())
        self.model_version = model_version
        self.day = simulator.get_state()["simulation_day"]
        self.cursor = self.event_sequence = self.decision_sequence = 0
        self.last_synced_seconds = 0
        self.forecasts = {}
        self.decisions = {}
        self.status = "created"
        init_db(self.path)
        scenario = simulator.get_scenario()
        config = {"scenario": scenario, "map": simulator.get_map(),
                  "scope": "shared simulation; no user identity"}
        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO simulation_runs(run_id,status,policy_name,config_json,model_version,rule_version) "
                "VALUES (?,'created','auto_manual',?,?,?)",
                (self.run_id, encode(config), model_version, scenario.get("rule_version")),
            )
        self.sync(status="created")

    @staticmethod
    def recover_open_runs(path=None):
        """Single-process startup preserves history but does not resume old state."""
        init_db(path)
        with connect_db(path) as connection:
            connection.execute(
                "UPDATE simulation_runs SET status='interrupted', ended_at=? "
                "WHERE status IN ('created','running','paused')", (utc_now(),))

    def sync(self, status=None, source="system"):
        state = self.simulator.get_state()
        if state["simulation_day"] != self.day:
            raise RuntimeError("Flush the old day and call begin_next_day() after next_day().")
        history = self.simulator.get_history()
        if len(history) < self.cursor:
            raise RuntimeError("History was cleared before it was flushed.")
        # Midnight ends a day, not the shared run.
        status = status or ("running" if state["is_running"] else "paused")
        if self.status in TERMINAL:
            status = self.status
        pending = history[self.cursor:]
        if not pending and status == self.status:
            self.last_synced_seconds = state["simulation_time_seconds"]
            return
        with connect_db(self.path) as connection:
            for offset, event in enumerate(pending):
                physical = event["type"] in (
                    "measurement", "arrival", "purification_on", "purification_off", "day_finished")
                connection.execute(
                    "INSERT INTO activity_events(run_id,simulation_day,event_sequence,time_seconds,"
                    "event_type,room_id,control_source,details_json) VALUES (?,?,?,?,?,?,?,?)",
                    (self.run_id, self.day, self.event_sequence + offset, event["time_seconds"],
                     event["type"], event.get("room") or event.get("destination"),
                     "system" if physical else source, encode(event)),
                )
                if event["type"] == "measurement":
                    connection.execute(
                        "INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,"
                        "source_minute,pm25) VALUES (?,?,?,?,?,?)",
                        (self.run_id, self.day, event["room"], event["measured_at_seconds"],
                         event["source_minute"], event["pm25"]),
                    )
            connection.execute(
                "UPDATE simulation_runs SET status=?, "
                "started_at=CASE WHEN ?='running' THEN COALESCE(started_at,?) ELSE started_at END, "
                "ended_at=CASE WHEN ? THEN COALESCE(ended_at,?) ELSE ended_at END WHERE run_id=?",
                (status, status, utc_now(), status in TERMINAL, utc_now(), self.run_id),
            )
        self.cursor = len(history)
        self.event_sequence += len(pending)
        self.last_synced_seconds = state["simulation_time_seconds"]
        self.status = status

    def begin_next_day(self):
        state = self.simulator.get_state()
        if state["simulation_day"] != self.day + 1 or self.last_synced_seconds != 86400:
            raise RuntimeError("Save the completed day before starting the next day.")
        if self.status in TERMINAL:
            raise RuntimeError("A closed run cannot start another day.")
        self.day += 1
        self.cursor = self.event_sequence = self.decision_sequence = 0
        self.forecasts.clear()
        self.decisions.clear()
        self.last_synced_seconds = 0
        self.sync()
        # Store each day's environment settings internally, never as AI observations.
        self.record_event("day_started", {"scenario": self.simulator.get_scenario()})

    def previous_days(self):
        """Return today's preceding 14 calendar days, scoped to this run only."""
        today = self.simulator.get_state()["simulation_day"]
        if today != self.day:
            raise RuntimeError("Recorder day is out of sync.")
        first = max(1, today - 14)
        days = {day: {room: [] for room in ROOMS} for day in range(first, today)}
        if not days:
            return []
        with connect_db(self.path) as connection:
            rows = connection.execute(
                "SELECT simulation_day,room_id,measured_at_seconds,pm25 FROM measurements "
                "WHERE run_id=? AND simulation_day>=? AND simulation_day<? "
                "AND measured_at_seconds<86400 ORDER BY simulation_day,measured_at_seconds,room_id",
                (self.run_id, first, today),
            ).fetchall()
        for row in rows:
            days[row["simulation_day"]][row["room_id"]].append(
                (row["measured_at_seconds"], row["pm25"]))
        return list(days.values())

    def save_forecast(self, forecast, observations, previous_days):
        from ai.predict import FEATURES, HISTORY_FEATURES, recent_features
        reference = int(forecast["reference_minute"] * 60)
        inputs = {}
        for room in ROOMS:
            reading = observations.get(room) or {}
            measured = reading.get("measured_at_seconds")
            age = None if measured is None else (reference - measured) / 60
            values = [room, reference // 3600, reference % 3600 // 60, reading.get("pm25"), age]
            values += recent_features(previous_days, room, forecast["target_minute"])
            inputs[room] = dict(zip(FEATURES + HISTORY_FEATURES, values))
            inputs[room]["history_first_day"] = max(1, self.day - 14)
            inputs[room]["history_last_day"] = self.day - 1
        signature = encode({"forecast": forecast, "observations": observations, "inputs": inputs})
        key = (self.day, reference)
        if key in self.forecasts:
            if signature != self.forecasts[key]:
                raise RuntimeError("Conflicting forecasts for the same day and time.")
            return
        with connect_db(self.path) as connection:
            for room, value in forecast["predictions"].items():
                reading = observations.get(room) or {}
                measured = reading.get("measured_at_seconds")
                connection.execute(
                    "INSERT INTO predictions(run_id,simulation_day,room_id,reference_seconds,"
                    "target_seconds,status,predicted_pm25,last_measured_pm25,last_measured_at_seconds,"
                    "observation_age_seconds,model_version,input_features_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (self.run_id, self.day, room, reference, int(forecast["target_minute"] * 60),
                     forecast["status"], value, reading.get("pm25"), measured,
                     None if measured is None else reference - measured,
                     self.model_version, encode(inputs[room])),
                )
        self.forecasts[key] = signature

    def save_decision(self, decision, source="automatic", key=None):
        signature = encode(decision)
        identity = (self.day, key)
        if key is not None and identity in self.decisions:
            if self.decisions[identity] != signature:
                raise RuntimeError("Conflicting decisions with the same identity.")
            return
        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO decisions(run_id,simulation_day,decision_sequence,decided_at_seconds,"
                "action,target_room,reason,control_source,details_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (self.run_id, self.day, self.decision_sequence, decision["decided_at_seconds"],
                 decision["action"], decision["target_room"], decision["reason"], source, signature),
            )
        self.decision_sequence += 1
        if key is not None:
            self.decisions[identity] = signature

    def record_event(self, event_type, details, source="system"):
        self.sync(source=source)
        with connect_db(self.path) as connection:
            connection.execute(
                "INSERT INTO activity_events(run_id,simulation_day,event_sequence,time_seconds,"
                "event_type,control_source,details_json) VALUES (?,?,?,?,?,?,?)",
                (self.run_id, self.day, self.event_sequence,
                 self.simulator.get_state()["simulation_time_seconds"], event_type, source, encode(details)),
            )
        self.event_sequence += 1

    def finish(self, reason):
        if reason not in TERMINAL:
            raise ValueError("Invalid run ending reason.")
        self.sync(status=reason)
