"""Run isolated checks: python -m backend.verify_persistence."""

import asyncio
from collections import deque
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from backend.database import SCHEMA, TABLES, connect_db, init_db, table_counts
from backend.repository import ROOMS, RunRecorder
from simulation import Simulator


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def verify_schema():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "legacy.db"
        # Reconstruct exactly the preceding single-day schema for migration testing.
        legacy = SCHEMA.replace(
            "    simulation_day INTEGER NOT NULL DEFAULT 1\n"
            "        CHECK (typeof(simulation_day)='integer' AND simulation_day >= 1),\n", "")
        legacy = legacy.replace("    input_features_json TEXT NOT NULL DEFAULT '{}',\n", "")
        legacy = legacy.replace("run_id, simulation_day,", "run_id,")
        with sqlite3.connect(path) as connection:
            connection.executescript(legacy + "\nPRAGMA user_version=1;")
            connection.execute("INSERT INTO simulation_runs(run_id) VALUES ('legacy')")
            connection.execute("INSERT INTO measurements(run_id,room_id,measured_at_seconds,source_minute,pm25) "
                               "VALUES ('legacy','kitchen',31300,521,23.5)")
            connection.execute("INSERT INTO predictions(run_id,room_id,reference_seconds,target_seconds,status,"
                               "predicted_pm25) VALUES ('legacy','kitchen',31800,33600,'ok',25)")
            connection.execute("INSERT INTO decisions(run_id,decision_sequence,decided_at_seconds,action,"
                               "target_room,reason) VALUES ('legacy',0,31800,'move','kitchen','test')")
            connection.execute("INSERT INTO activity_events(run_id,event_sequence,time_seconds,event_type) "
                               "VALUES ('legacy',0,31300,'measurement')")
        before = table_counts(path)
        with connect_db(path) as connection:
            originals = {t: [dict(row) for row in connection.execute(f"SELECT * FROM {t}")]
                         for t in TABLES}
        init_db(path)
        require(table_counts(path) == before, "Migration changed row counts.")
        with connect_db(path) as connection:
            require(connection.execute("PRAGMA user_version").fetchone()[0] == 2, "Migration did not update version.")
            for table in TABLES:
                migrated = [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]
                for old, new in zip(originals[table], migrated):
                    require(all(new[key] == value for key, value in old.items()), "Migration changed old data.")
                    if table != "simulation_runs":
                        require(new["simulation_day"] == 1, "Legacy day was not assigned to 1.")
            require(connection.execute("PRAGMA foreign_key_check").fetchall() == [], "Broken parent links.")
        require(len(list(Path(folder).glob("*.before_v2_*.db"))) == 1, "Migration backup was not created.")
        init_db(path)
        require(table_counts(path) == before, "Repeat initialization changed records.")
        for day in [2, 3]:
            with connect_db(path) as connection:
                connection.execute("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
                                   "VALUES ('legacy',?,'kitchen',31300,25)", (day,))
        for statement, args in [
            ("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
             "VALUES ('legacy',2,'kitchen',31300,25)", ()),
            ("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
             "VALUES ('missing',1,'kitchen',100,10)", ()),
            ("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
             "VALUES ('legacy',0,'kitchen',100,10)", ()),
        ]:
            try:
                with connect_db(path) as connection:
                    connection.execute(statement, args)
            except sqlite3.IntegrityError:
                pass
            else:
                raise AssertionError("An invalid or duplicate measurement was accepted.")
        # A failed migration must roll back all table changes.
        broken = Path(folder) / "broken.db"
        with sqlite3.connect(broken) as connection:
            connection.executescript(legacy + "\nPRAGMA user_version=1;")
            connection.execute("INSERT INTO simulation_runs(run_id) VALUES ('broken')")
            connection.execute("PRAGMA ignore_check_constraints=ON")
            connection.execute("INSERT INTO measurements(run_id,room_id,measured_at_seconds,pm25) "
                               "VALUES ('broken','kitchen',10,-1)")
        try:
            init_db(broken)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("Bad legacy data should prevent migration.")
        with connect_db(broken) as connection:
            require(connection.execute("PRAGMA user_version").fetchone()[0] == 1, "Failed migration changed version.")
            require(connection.execute("SELECT pm25 FROM measurements").fetchone()[0] == -1,
                    "Failed migration changed legacy data.")
    print("PASS: v1 backup/migration/rollback, old rows and IDs, repeat initialization, day keys, and constraints")


def verify_query_window(path):
    sim = Simulator(events=())
    store = RunRecorder(sim, "query-fixture", path)
    with connect_db(path) as connection:
        connection.execute("INSERT INTO simulation_runs(run_id) VALUES ('another-run')")
        for day in range(1, 22):
            connection.execute("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
                               "VALUES (?,?, 'kitchen',31300,?)", (store.run_id, day, day))
        connection.execute("INSERT INTO measurements(run_id,simulation_day,room_id,measured_at_seconds,pm25) "
                           "VALUES ('another-run',7,'kitchen',31300,9999)")
    # Calendar positions are query fixtures, not generated application measurements.
    sim.simulation_day = store.day = 8
    history = store.previous_days()
    require([x["kitchen"][0][1] for x in history] == list(range(1, 8)), "Day 8 did not use days 1-7 only.")
    sim.simulation_day = store.day = 20
    history = store.previous_days()
    require([x["kitchen"][0][1] for x in history] == list(range(6, 20)), "The 14-day window or run scope is wrong.")


def verify_actual_second_timestamp(path):
    sim = Simulator(events=())
    store = RunRecorder(sim, "timestamp-check", path)
    sim.start()
    for _ in range(2):
        while not sim.get_state()["finished"]:
            sim.step()
        store.sync()
        sim.next_day()
        store.begin_next_day()
    while sim.get_state()["simulation_time_seconds"] < 31200:
        sim.step()
    sim.move_to("kitchen")
    while sim.get_state()["remaining_steps"]:
        sim.step()
    store.sync()
    with connect_db(path) as connection:
        row = connection.execute("SELECT simulation_day,measured_at_seconds FROM measurements "
                                 "WHERE run_id=? AND room_id='kitchen' ORDER BY measurement_id DESC LIMIT 1",
                                 (store.run_id,)).fetchone()
        require(tuple(row) == (3, 31300), "The day-3 08:41:40 arrival was not saved exactly.")


def main():
    verify_schema()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "checks.db"
        verify_query_window(path)
        verify_actual_second_timestamp(path)
        with patch.dict(os.environ, {"AIR_PURIFIER_DB_PATH": str(path)}):
            from backend import main as api
            api.simulator = Simulator(tick_seconds=60)

            class ForbiddenMemoryHistory(deque):
                def __iter__(self):
                    raise AssertionError("Inference used simulator.previous_days instead of the database.")

            api.simulator.previous_days = ForbiddenMemoryHistory(maxlen=14)
            api.recorder = None
            api.latest_prediction = api.latest_decision = api.last_prediction_seconds = None
            api.selected_mode = api.active_mode = "auto"
            store = api.ensure_recorder()
            original_model = api.predictor.model

            class TracedModel:
                inputs = None
                def predict(self, inputs):
                    self.inputs = inputs.copy()
                    return original_model.predict(inputs)

            traced = TracedModel()
            api.predictor.model = traced
            def forbidden_truth():
                raise AssertionError("Inference requested hidden ground truth.")
            api.simulator.get_ground_truth = forbidden_truth
            asyncio.run(api.start())
            with contextlib.redirect_stdout(io.StringIO()):
                while (api.simulator.simulation_day == 1 or
                       api.simulator.get_state()["simulation_time_seconds"] <= 2400):
                    api.advance_simulation()
            require(api.simulator.simulation_day == store.day == 2, "Midnight did not keep the recorder in sync.")
            require(traced.inputs is not None and traced.inputs.days_observed.max() > 0,
                    "The actual model did not receive historical DB features.")
            with connect_db(path) as connection:
                require(connection.execute("SELECT COUNT(*) FROM activity_events WHERE run_id=? "
                                           "AND simulation_day=1 AND event_type='day_finished' "
                                           "AND time_seconds=86400", (store.run_id,)).fetchone()[0] == 1,
                        "Midnight lost the final day event.")
                require(connection.execute("SELECT COUNT(*) FROM measurements WHERE run_id=? "
                                           "AND simulation_day=2 AND measured_at_seconds=0",
                                           (store.run_id,)).fetchone()[0] == 1, "The new-day initial measurement is missing.")
                require(connection.execute("SELECT ended_at FROM simulation_runs WHERE run_id=?",
                                           (store.run_id,)).fetchone()[0] is None, "Midnight closed the run.")
                rows = connection.execute("SELECT * FROM predictions WHERE run_id=? AND simulation_day=2 "
                                          "AND status='ok'", (store.run_id,)).fetchall()
                require(bool(rows), "No valid second-day forecasts were saved.")
                for row in rows:
                    inputs = json.loads(row["input_features_json"])
                    require(inputs["history_last_day"] == 1, "Today's history leaked into inputs.")
                    reading = connection.execute("SELECT * FROM measurements WHERE run_id=? AND simulation_day=2 "
                                                 "AND room_id=? AND measured_at_seconds<=? "
                                                 "ORDER BY measured_at_seconds DESC LIMIT 1",
                                                 (store.run_id, row["room_id"], row["reference_seconds"])).fetchone()
                    require(reading["pm25"] == row["last_measured_pm25"]
                            and reading["measured_at_seconds"] == row["last_measured_at_seconds"],
                            "Forecast did not use the latest same-day observation.")
            asyncio.run(api.pause())
            counts = table_counts(path)
            for _ in range(3):
                asyncio.run(api.get_status())
                asyncio.run(api.get_history())
                asyncio.run(api.predict())
                store.previous_days()
                store.sync()
            require(table_counts(path) == counts, "Reads or repeated sync duplicated records.")
            asyncio.run(api.start())
            require(api.recorder.run_id == store.run_id, "Resume changed the run ID.")
            asyncio.run(api.pause())
            cursor = store.cursor
            api.simulator.start()
            with patch("backend.repository.connect_db", side_effect=sqlite3.OperationalError("test")):
                try:
                    store.sync()
                except sqlite3.OperationalError:
                    pass
            require(store.cursor == cursor, "A failed write advanced the event cursor.")
            store.sync()
            old_run = store.run_id
            before_reset = {}
            with connect_db(path) as connection:
                for t in TABLES[1:]:
                    before_reset[t] = connection.execute(f"SELECT COUNT(*) FROM {t} WHERE run_id=?",
                                                        (old_run,)).fetchone()[0]
            asyncio.run(api.reset())
            require(api.recorder.run_id != old_run and api.simulator.simulation_day == 1,
                    "Reset did not create a new day-1 run.")
            require(api.recorder.previous_days() == [], "Reset inherited a different run's past measurements.")
            with connect_db(path) as connection:
                for t, count in before_reset.items():
                    require(connection.execute(f"SELECT COUNT(*) FROM {t} WHERE run_id=?",
                                               (old_run,)).fetchone()[0] == count, "Reset erased old records.")
            asyncio.run(api.set_mode(api.ModeRequest(mode="manual")))
            asyncio.run(api.move(api.MoveRequest(target_room="kitchen")))
            asyncio.run(api.start())
            while api.simulator.get_state()["remaining_steps"]:
                api.advance_simulation()
            asyncio.run(api.pause())
            api.predictor.model = original_model
            print(json.dumps({"result": "PASS", "scope": "Temporary DB, actual model and simulator; no Cognito login test",
                              "checks": ["migration and backup", "same run across midnight", "day 3 at 31300 seconds",
                                         "day 8 uses days 1-7", "rolling 14 days and run isolation",
                                         "real model uses DB history", "current observation trace", "read-only GET requests",
                                         "retry cursor", "pause/resume", "reset retention and empty history", "manual mode"]}, indent=2))
    print("Temporary verification data removed; app.db was not changed.")


if __name__ == "__main__":
    main()
