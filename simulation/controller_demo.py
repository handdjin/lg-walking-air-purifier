"""python3 -m simulation.controller_demo: 예시 예측값으로 목적지 선택 시연."""

from . import Simulator
from .controller import decide_and_move


def main():
    print("아래 숫자는 연결 테스트용 예시이며 실제 AI 예측이 아닙니다.")
    examples = [
        ("주방 위험", {"living_room": 20, "kitchen": 60, "bedroom": 40}),
        ("침실 위험", {"living_room": 20, "kitchen": 40, "bedroom": 60}),
        ("현재 방 선택", {"living_room": 60, "kitchen": 20, "bedroom": 20}),
        ("모든 방 낮음", {"living_room": 20, "kitchen": 20, "bedroom": 20}),
    ]
    for label, predictions in examples:
        sim = Simulator(events=())
        result = decide_and_move(sim, predictions)
        decision = result["decision"]
        print(f"\n{label}: {predictions}")
        for room, detail in decision["rooms"].items():
            print(f"  {room}: 이동 {detail['travel_seconds']}초, 점수 {detail['score']:.2f}")
        print("판단:", decision["action"], decision["target_room"], decision["reason"])
        sim.start()
        while sim.get_state()["remaining_steps"]:
            sim.step()
        state = sim.get_state()
        print("결과:", state["current_room"], state["position"],
              f"가상 {state['simulation_time_seconds']}초")


if __name__ == "__main__":
    main()
