
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from simulation import Simulator
import asyncio
from contextlib import asynccontextmanager
from ai.predict import Predictor
from simulation.controller import decide_and_move

simulator = Simulator()
predictor = Predictor()
latest_prediction = None
latest_decision = None

def initial_patrol():
    state = simulator.get_state()

    # 이동 중이면 기존 이동을 유지
    if state["remaining_steps"] > 0:
        return

    # 아직 측정하지 않은 방으로 이동
    for room in ["living_room", "kitchen", "bedroom"]:
        if state["observations"][room]["pm25"] is None:
            simulator.move_to(room)
            return

def auto_decision():
    global latest_prediction, latest_decision

    state = simulator.get_state()

    if state["remaining_steps"] > 0 or state["finished"]:
        return

    if state["simulation_time_seconds"] % 600 != 0:
        return

    observations = {
        room: {
            "pm25": reading["pm25"],
            "measured_minute": reading["source_minute"]
        }
        for room, reading in state["observations"].items()
    }

    result = predictor.predict_rooms(
        now_minute=state["environment_minute"],
        observations=observations
    )

    latest_prediction = result

    if result["status"] == "ok":
        decision = decide_and_move(
            simulator,
            result["predictions"]
        )

        latest_decision = decision["decision"]

        print("AI 판단:", latest_decision)
    else:
        latest_decision = None
        
async def simulation_loop():
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

# Expo 웹 버전 테스트를 위한 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 앱에서 전달할 이동 요청 형식
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
        "ai_decision": latest_decision
    }
    
@app.post("/move")
async def move(request: MoveRequest):
    try:
        return simulator.move_to(request.target_room)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
@app.post("/step")
async def step():
    return simulator.step()
        
@app.get("/map")
async def get_map():
    return simulator.get_map()

@app.post("/reset")
async def reset():
    global latest_prediction, latest_decision

    state = simulator.reset()
    latest_prediction = None
    latest_decision = None

    return state

@app.post("/start")
async def start():
    try:
        return simulator.start()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/pause")
async def pause():
    return simulator.pause()

@app.get("/predict")
async def predict():
    state = simulator.get_state()

    observations = {
        room: {
            "pm25": reading["pm25"],
            "measured_minute": reading["source_minute"]
        }
        for room, reading in state["observations"].items()
    }

    return predictor.predict_rooms(
        now_minute=state["environment_minute"],
        observations=observations
    )