# Shared Multiday SQLite History

This integration targets repository revision `71ea253`. It preserves Cognito
authentication, automatic/manual mode, destination rules, purification rules,
HTTP polling, and the memory-based `/history` response.

## Files

| File | Responsibility |
| --- | --- |
| `backend/database.py` | Schema v2 and transactional migration from v1 |
| `backend/repository.py` | Record insertion and previous-day measurement queries |
| `backend/main.py` | Event, forecast, control, midnight, and reset integration |
| `ai/predict.py` | Optional explicit `previous_days` argument; existing callers keep their default behavior |
| `backend/verify_persistence.py` | Isolated migration and real-model integration checks |
| `backend/show_records.py` | Read-only local history inspection |

## Identity and virtual time

- The five tables remain `simulation_runs`, `measurements`, `predictions`,
  `decisions`, and `activity_events`.
- The four child tables add integer `simulation_day`, starting at 1.
- Virtual timestamps are seconds since midnight, not real timestamps.
- Measurements are unique by `(run_id, simulation_day, room_id, measured_at_seconds)`.
- Forecasts are unique by `(run_id, simulation_day, room_id, reference_seconds)`.
- Decision/event sequences restart daily and are unique within a run and day.
- Real storage timestamps use UTC separately.

At midnight, the old day's history is flushed **before** `Simulator.next_day()`.
The recorder then changes its day and saves the next day's initial events.
The same `run_id` continues and is not marked completed at midnight.
Reset closes the preceding run, creates a new UUID, and starts at day 1.
Pause/resume preserves both run and day.

## Forecast inputs from the database

The live backend queries only the same run's days
`max(1, today - 14)` through `today - 1`. It returns one dictionary per calendar
day, with all three room keys and lists of `(measured_seconds, pm25)` pairs.
Days or rooms without measurements have empty lists. End-of-day 86400-second
readings remain stored but are excluded from previous-day features, matching
the simulator's original history behavior.

Today, later days, and other runs are excluded. Day 8 uses days 1-7;
day 20 uses days 6-19. A new reset run has no past days.
Today's latest observations and exact observation age still come from simulator
state. Hidden current concentrations and future pollution schedules are not inputs.

`recent_features()` and the existing `uniform20_model.joblib` are reused.
The feature calculations are unchanged. DB-connected online inference passes
explicit history; offline generator/evaluator callers retain the simulator
history default. No retraining or CSV import is required for this integration.

Forecast records add `input_features_json` containing the eight feature values
and the permitted history-day range for auditing. This field is not exposed as
a new public API. Unavailable forecasts remain NULL with their status.

## Existing DB migration

```bash
python -m backend.database
```

Schema v1 is backed up using SQLite's backup API, including committed WAL data,
to `backend/data/app.before_v2_<UTC timestamp>.db` before modification.
The four child tables are rebuilt in a single transaction to replace old UNIQUE
constraints. Original IDs, timestamps, values, run links, and run records are retained.
Legacy single-day records receive day 1; their unrecorded historical dates cannot
be inferred. New columns use defaults. A failed migration rolls back changes.
Unknown schemas or unexpected user tables stop migration rather than erase data.
Repeated v2 initialization does not duplicate or clear records.

Do not delete app.db, remove backup files during review, or change the schema
version number manually. Stop the backend before migration.

## Verification

Run from the project root, after saving all changed files:

```bash
python -m backend.database --verify
python -m backend.verify_persistence
```

Checks use temporary databases and never modify app.db. They test migration,
backup, rollback, constraints, midnight retention, actual day-3 kitchen arrival at
31300 seconds, day-8 and rolling-14-day windows, same-run isolation, the real
model using DB history rather than memory history, observation input traces,
read-only requests, duplicate prevention, retry cursors, pause/resume, reset,
and manual mode. This is not a Cognito login or physical-device test, or an
accuracy/purification-effectiveness claim.

## Run and inspect

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Use exactly one process; do not add `--workers` or `--reload`. Use the existing
authenticated app, or provide an authorized Cognito access token in API docs.
Missing credentials still produce HTTP 401. Do not remove authentication to test storage.

In another terminal:

```bash
python -m backend.show_records
python -m backend.show_records --day 3
python -m backend.database
```

The inspector opens SQLite in read-only mode. It prints recent runs, measurement
counts by day, and recent rows for the selected run/day. The database command
prints totals across all runs. `/status`, `/history`, `/map`, and `/predict` do
not write records; `/predict` uses DB history but is an on-demand unsaved forecast.
Scheduled forecasts are persisted. Pause simulation before comparing counts.

## Scope

The shared simulation stores no user identities, passwords, or tokens. The DB
preserves history across resets/restarts, but it does not restore a running
simulation after a process restart. Startup marks old open runs interrupted and
creates fresh state. A storage-loop error pauses the simulation; resolve the
error and reset before continuing. Separate operations use short transactions,
so a crash may leave a partial final operation. This is not crash-safe execution
replay or a concurrent multi-user simulation system.

Do not import all generated training CSVs into this runtime database.
Do not remove the memory `/history` endpoint or replace its response format.

## Git exclusions

```gitignore
/backend/data/*.db
/backend/data/*.db-wal
/backend/data/*.db-shm
/backend/data/*.db-journal
```

These patterns also exclude migration backups. Keep credentials, actual DBs,
their WAL/SHM files, and local data/model backups out of commits.
