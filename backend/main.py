import asyncio
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai.predict import Predictor, predict_from_simulator
from backend.repository import RunRecorder
from simulation import Simulator
from simulation.controller import choose_destination

from fastapi import Depends
from backend.auth import verify_token


simulator = Simulator()
predictor = Predictor()
MODEL_FILE = Path(__file__).resolve().parents[1] / "ai/artifacts/uniform20_model.joblib"
MODEL_VERSION = "sha256:" + hashlib.sha256(MODEL_FILE.read_bytes()).hexdigest()
recorder = None


def ensure_recorder():
    global recorder
    if recorder is None:
        recorder = RunRecorder(simulator, MODEL_VERSION)
    if recorder.simulator is not simulator:
        raise RuntimeError("Create a new recorder when replacing the simulator.")
    return recorder

latest_prediction = None
latest_decision = None
last_prediction_seconds = None


Mode = Literal["auto", "manual"]
selected_mode: Mode = "auto"
active_mode: Mode = "auto"


def initial_patrol():
    """Visit rooms that have not been measured."""
    state = simulator.get_state()

    # Preserve an existing route. Stopped, returning, or docked devices stay put.
    if state["remaining_steps"] > 0 or state["device_state"] != "running":
        return

    for room in ["living_room", "kitchen", "bedroom"]:
        if state["observations"][room]["pm25"] is None:
            simulator.move_to(room)
            return


def auto_decision():
    """Forecast at 10-minute boundaries and request a decision."""
    global latest_prediction
    global latest_decision
    global last_prediction_seconds

    state = simulator.get_state()

    if state["finished"]:
        return

    seconds = state["simulation_time_seconds"]

    if seconds % 600 == 0 and last_prediction_seconds != seconds:
        store = ensure_recorder()
        store.sync(source="automatic" if active_mode == "auto" else "manual")
        previous_days = store.previous_days()
        latest_prediction = predict_from_simulator(
            predictor, simulator, previous_days=previous_days)
        store.save_forecast(latest_prediction, state["observations"], previous_days)
        last_prediction_seconds = seconds
        latest_decision = None
        if (active_mode == "auto" and latest_prediction["status"] == "ok"
                and not state["remaining_steps"] and state["device_state"] == "running"):
            latest_decision = choose_destination(
                simulator, latest_prediction["predictions"], threshold=20)
            store.save_decision(latest_decision, key=f"forecast:{seconds}")

    if (active_mode != "auto" or not latest_decision or state["remaining_steps"]
            or state["device_state"] != "running"
            or latest_decision["decided_at_seconds"] != seconds - seconds % 600):
        return
    arrival = simulator.last_arrival_seconds
    if arrival is not None and seconds - arrival < 600:
        return
    if latest_decision["action"] == "move" and seconds % 600 == 0:
        simulator.move_to(latest_decision["target_room"])
        ensure_recorder().sync(source="automatic")
        return

    phase = ((simulator.simulation_day - 1) * 3 % 10) * 60
    if (latest_decision["action"] == "wait" and seconds % 600 == phase
            and not state["is_purifying"]):
        ages = {room: reading["age_seconds"] for room, reading in state["observations"].items()
                if room != state["current_room"] and reading["age_seconds"] is not None}
        limit = (120 if simulator.simulation_day <= 7 else 180) * 60
        if ages:
            room = max(ages, key=ages.get)
            if ages[room] >= limit:
                simulator.move_to(room)
                latest_decision = {**latest_decision, "action": "move",
                                   "reason": "stale_measurement", "target_room": room}
                store = ensure_recorder()
                store.save_decision({**latest_decision, "decided_at_seconds": seconds,
                                     "forecast_reference_seconds": latest_decision["decided_at_seconds"]},
                                    key=f"stale:{seconds}")
                store.sync(source="automatic")


def advance_simulation():
    global active_mode, latest_prediction, latest_decision, last_prediction_seconds
    if simulator.get_state()["is_running"]:
        store = ensure_recorder()
        if active_mode == "auto":
            initial_patrol()
        auto_decision()
        state = simulator.step()
        # Flush measurements and day_finished BEFORE next_day() clears history.
        store.sync(source="automatic" if active_mode == "auto" else "manual")
        if state["finished"]:
            simulator.next_day()
            store.begin_next_day()
            latest_prediction = latest_decision = last_prediction_seconds = None
        if not state["remaining_steps"]:
            active_mode = selected_mode
    return status()


async def simulation_loop():
    """Advance the simulation through one server-controlled loop."""
    while True:
        try:
            advance_simulation()
        except Exception:
            import traceback

            traceback.print_exc()
            simulator.pause()
            if recorder is not None:
                try:
                    recorder.finish("error")
                except Exception:
                    traceback.print_exc()

        await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Exactly one backend worker owns the shared in-memory simulation.
    RunRecorder.recover_open_runs()
    store = ensure_recorder()
    # The app has device controls only, so the simulation clock runs from server start.
    # /start, /pause, and /reset remain for demo setup and testing.
    simulator.start()
    store.sync(source="system")
    task = asyncio.create_task(simulation_loop())

    try:
        yield
    finally:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass
        simulator.pause()
        recorder.finish("interrupted")


app = FastAPI(
    lifespan=lifespan,
    dependencies=[Depends(verify_token)],
)

# Allow requests from the Expo web client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class MoveRequest(BaseModel):
    target_room: str


class ModeRequest(BaseModel):
    mode: Mode


@app.get("/")
def home():
    return {"message": "FastAPI is working!"}


def status():
    return {
        **simulator.get_state(),
        "run_id": recorder.run_id if recorder is not None else None,
        "mode": selected_mode,
        "active_mode": active_mode,
        "ai_prediction": latest_prediction,
        "ai_decision": latest_decision,
    }


@app.get("/status")
async def get_status():
    return status()


@app.post("/mode")
async def set_mode(request: ModeRequest):
    global selected_mode, active_mode, latest_decision
    store = ensure_recorder()
    selected_mode = request.mode
    if not simulator.get_state()["remaining_steps"]:
        active_mode = selected_mode
    if selected_mode == "manual":
        latest_decision = None
    store.record_event("mode_requested", {"mode": selected_mode, "active_mode": active_mode}, "manual")
    return status()


@app.post("/move")
async def move(request: MoveRequest):
    if selected_mode != "manual" or active_mode != "manual":
        raise HTTPException(status_code=409, detail="Manual mode must be active to select a room.")
    try:
        store = ensure_recorder()
        simulator.move_to(request.target_room)
        store.sync(source="manual")
        state = simulator.get_state()
        store.save_decision({"decided_at_seconds": state["simulation_time_seconds"],
                             "action": "move" if state["remaining_steps"] else "stay",
                             "target_room": request.target_room, "reason": "manual_request"},
                            source="manual")
        return status()
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.post("/step")
async def step():
    return advance_simulation()


@app.get("/map")
async def get_map():
    return simulator.get_map()


@app.post("/reset")
async def reset():
    global latest_prediction
    global latest_decision
    global last_prediction_seconds

    global selected_mode, active_mode, recorder
    previous = ensure_recorder()
    previous.finish("reset")
    simulator.reset()
    recorder = RunRecorder(simulator, MODEL_VERSION, path=previous.path)
    selected_mode = active_mode = "auto"

    latest_prediction = None
    latest_decision = None
    last_prediction_seconds = None

    return status()


@app.post("/start")
async def start():
    try:
        store = ensure_recorder()
        if store.status in ("error", "reset", "interrupted", "completed"):
            raise HTTPException(status_code=409, detail="Reset before starting a new run.")
        simulator.start()
        store.sync(source="manual")
        return status()
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.post("/pause")
async def pause():
    store = ensure_recorder()
    simulator.pause()
    store.sync(source="manual")
    return status()


def device_command(action):
    """Run a device control. Time and pollution keep changing in every device state."""
    global latest_decision
    store = ensure_recorder()
    try:
        action()
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    if simulator.get_state()["device_state"] != "running":
        latest_decision = None  # No automatic decision applies while stopped or docked
    store.sync(source="manual")
    return status()


@app.post("/device/start")
async def start_device():
    """Resume after a stop or leave the dock."""
    return device_command(simulator.start_operation)


@app.post("/device/stop")
async def stop_device():
    """Stop moving, measuring, and purifying in place."""
    return device_command(simulator.stop_operation)


@app.post("/device/dock")
async def return_device_to_dock():
    """Return to the charging dock and wait there."""
    return device_command(simulator.return_to_dock)


@app.get("/predict")
async def predict():
    if recorder is None:
        raise HTTPException(status_code=503, detail="Simulation storage is not initialized.")
    return predict_from_simulator(predictor, simulator, previous_days=recorder.previous_days())

@app.get("/history")
async def get_history():
    return simulator.get_history()
