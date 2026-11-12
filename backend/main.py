
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from simulation import Simulator

app = FastAPI()
simulator = Simulator()

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
def get_status():
    return simulator.get_state()

@app.post("/move")
def move(request: MoveRequest):
    try:
        return simulator.move_to(request.target_room)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
@app.post("/step")
def step():
    return simulator.step()
        
@app.get("/map")
def get_map():
    return simulator.get_map()

@app.post("/reset")
def reset():
    return simulator.reset()