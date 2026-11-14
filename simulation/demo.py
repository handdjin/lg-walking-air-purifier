"""python3 -m simulation.demo 로 거실 → 주방 → 침실 → 거실을 시연한다."""

import argparse
import time

from .simulator import Simulator


def show(simulator):
    state = simulator.get_state()
    location = state["room_name"] or "문 통과 중"
    print(simulator.render_map())
    print(f"위치: {location} {state['position']} | 상태: {state['status']}"
          f" | 남은 이동: {state['remaining_steps']}칸"
          f" | 가상 시간: {state['simulation_time_seconds']}초\n")


def main():
    parser = argparse.ArgumentParser(description="2D 지도에서 방 사이를 한 칸씩 이동합니다.")
    parser.add_argument("--delay", type=float, default=0,
                        help="출력 사이 대기 시간(초). 시연용이며 가상 이동 시간이 아닙니다.")
    args = parser.parse_args()
    if not 0 <= args.delay <= 5:
        parser.error("--delay는 0~5초 사이여야 합니다.")
    simulator = Simulator()
    simulator.start()
    print("# 벽 | X 장애물 | D 문 | . 바닥 | R 청정기")
    print("왼쪽: 거실 / 오른쪽 위: 주방 / 오른쪽 아래: 침실\n")
    show(simulator)
    for room in ("kitchen", "bedroom", "living_room"):
        print(f"목적지 요청: {room}")
        state = simulator.move_to(room)
        while state["status"] == "moving":
            if args.delay:
                time.sleep(args.delay)
            state = simulator.step()
            show(simulator)
        print(f"도착 완료: {state['room_name']}\n")
    try:
        simulator.move_to("bathroom")
    except ValueError as error:
        print(f"잘못된 이동 요청 처리: {error}")
    print(f"오류 후 위치: {simulator.get_state()['position']}")


if __name__ == "__main__":
    main()
