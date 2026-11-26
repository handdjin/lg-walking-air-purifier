import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai.predict import Predictor, predict_from_simulator
from simulation import Simulator
from simulation.controller import choose_destination

from fastapi import Depends
from backend.auth import verify_token


simulator = Simulator()
predictor = Predictor()

latest_prediction = None
latest_decision = None
last_prediction_seconds = None


Mode = Literal["auto", "manual"]
selected_mode: Mode = "auto"
active_mode: Mode = "auto"


def initial_patrol():
    """Visit rooms that have not been measured."""
    state = simulator.get_state()

    # Preserve an existing route.
    if state["remaining_steps"] > 0:
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
        latest_prediction = predict_from_simulator(predictor, simulator)
        last_prediction_seconds = seconds
        latest_decision = None
        if (active_mode == "auto" and latest_prediction["status"] == "ok"
                and not state["remaining_steps"]):
            latest_decision = choose_destination(
                simulator, latest_prediction["predictions"], threshold=20)

    if (active_mode != "auto" or not latest_decision or state["remaining_steps"]
            or latest_decision["decided_at_seconds"] != seconds - seconds % 600):
        return
    arrival = simulator.last_arrival_seconds
    if arrival is not None and seconds - arrival < 600:
        return
    if latest_decision["action"] == "move" and seconds % 600 == 0:
        simulator.move_to(latest_decision["target_room"])
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


def advance_simulation():
    global active_mode, latest_prediction, latest_decision, last_prediction_seconds
    if simulator.get_state()["is_running"]:
        if active_mode == "auto":
            initial_patrol()
        auto_decision()
        state = simulator.step()
        if state["finished"]:
            simulator.next_day()
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

        await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(simulation_loop())

    try:
        yield
    finally:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


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
    selected_mode = request.mode
    if not simulator.get_state()["remaining_steps"]:
        active_mode = selected_mode
    if selected_mode == "manual":
        latest_decision = None
    return status()


@app.post("/move")
async def move(request: MoveRequest):
    if selected_mode != "manual" or active_mode != "manual":
        raise HTTPException(status_code=409, detail="Manual mode must be active to select a room.")
    try:
        simulator.move_to(request.target_room)
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

    global selected_mode, active_mode
    simulator.reset()
    selected_mode = active_mode = "auto"

    latest_prediction = None
    latest_decision = None
    last_prediction_seconds = None

    return status()


@app.post("/start")
async def start():
    try:
        return simulator.start()
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.post("/pause")
async def pause():
    return simulator.pause()


@app.get("/predict")
async def predict():
    return predict_from_simulator(predictor, simulator)

@app.get("/history")
async def get_history():
    return simulator.get_history()