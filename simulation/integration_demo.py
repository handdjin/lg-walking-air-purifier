"""python3 -m simulation.integration_demo: 이동·환경·자동 정화 통합 비교."""

from . import Simulator
from .environment import PollutionEvent


def main():
    # 빠른 확인용 사건이다. 기본 하루 활동 시간표는 변경하지 않는다.
    events = (PollutionEvent("kitchen", "cooking", 0, 20),)
    scenarios = [Simulator(events=()), Simulator(events=events), Simulator(events=events)]
    for simulator in scenarios:
        simulator.start()
    cleaned = scenarios[2]
    print("시연: 00:00~00:20 주방 요리, 00:10에 거실에서 주방으로 출발")
    print("아래 농도는 검증용 내부 정답입니다. 앱에 표시할 관측값과 다릅니다.")
    print("가상 초 | 오염 없음 | 요리/방문 없음 | 요리/방문 정화 | 청정기 상태")
    for seconds in range(0, 3601, 10):
        if seconds == 600:
            cleaned.move_to("kitchen")
        if seconds in (0, 600, 700, 1200, 1800, 2400, 3600):
            values = [s.get_ground_truth()["pm25"]["kitchen"] for s in scenarios]
            print(f"{seconds:7} | {values[0]:9.2f} | {values[1]:14.2f} | "
                  f"{values[2]:14.2f} | {cleaned.get_state()['status']}")
        if seconds < 3600:
            for simulator in scenarios:
                simulator.step()
    print("\n실제 측정·자동 정화 기록:")
    for entry in cleaned.get_history():
        if entry["type"] in ("measurement", "purification_on", "purification_off"):
            print(entry)
    paused = cleaned.pause()
    assert cleaned.step() == paused
    print("\n일시정지 확인: step()을 호출해도 위치·시간·공기질이 유지됩니다.")
    reset = cleaned.reset()
    assert reset["simulation_time_seconds"] == 0 and reset["destination"] is None
    print("초기화 확인:", reset)


if __name__ == "__main__":
    main()
