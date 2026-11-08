
from fastapi import FastAPI, HTTPException
from simulation import Simulator

app = FastAPI()

# 서버 실행 시 시뮬레이터 하나 생성
simulator = Simulator()

@app.get("/")
def home():
    return {"message": "FastAPI is working!"}

@app.get("/status")
def get_status():
    return simulator.get_state()

@app.post("/move")
def move():
    try:
        return simulator.move_to("kitchen")
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
