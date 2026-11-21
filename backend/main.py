import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai.predict import Predictor, predict_from_simulator
from simulation import Simulator
from simulation.controller import decide_and_move


simulator = Simulator()
predictor = Predictor()

latest_prediction = None
latest_decision = None
last_prediction_seconds = None


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

    if seconds % 600 != 0:
        return

    # Process each prediction time only once.
    if last_prediction_seconds == seconds:
        return

    # Use actual measurement timestamps, including fractional minutes.
    result = predict_from_simulator(predictor, simulator)

    last_prediction_seconds = seconds
    latest_prediction = result

    # Keep an active route unchanged.
    if result["status"] == "ok" and state["remaining_steps"] == 0:
        response = decide_and_move(
            simulator,
            result["predictions"],
        )

        latest_decision = response["decision"]

        print("AI decision:", latest_decision)

    elif result["status"] != "ok":
        latest_decision = None


async def simulation_loop():
    """Advance the simulation through one server-controlled loop."""
    while True:
        try:
            state = simulator.get_state()

            if state["is_running"]:
                initial_patrol()
                auto_decision()
                simulator.step()

        except Exception:
            import traceback

            traceback.print_exc()
            simulator.pause()

        await asyncio.sleep(0.01)


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


app = FastAPI(lifespan=lifespan)

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


@app.get("/")
def home():
    return {"message": "FastAPI is working!"}


@app.get("/status")
async def get_status():
    return {
        **simulator.get_state(),
        "ai_prediction": latest_prediction,
        "ai_decision": latest_decision,
    }


@app.post("/move")
async def move(request: MoveRequest):
    try:
        return simulator.move_to(request.target_room)
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


@app.post("/step")
async def step():
    return simulator.step()


@app.get("/map")
async def get_map():
    return simulator.get_map()


@app.post("/reset")
async def reset():
    global latest_prediction
    global latest_decision
    global last_prediction_seconds

    state = simulator.reset()

    latest_prediction = None
    latest_decision = None
    last_prediction_seconds = None

    return state


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