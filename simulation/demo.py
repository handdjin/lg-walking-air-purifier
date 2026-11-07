"""프로젝트 루트에서 python3 -m simulation.demo 로 실행한다."""

from .simulator import Simulator


def main() -> None:
    simulator = Simulator()
    state = simulator.get_state()
    print(f"시작 위치: {state['room_name']} ({state['current_room']})")

    for room in ("kitchen", "bedroom"):
        state = simulator.move_to(room)
        print(f"이동 후 위치: {state['room_name']} ({state['current_room']})")

    try:
        simulator.move_to("bathroom")
    except ValueError as error:
        print(f"잘못된 이동 요청: {error}")

    state = simulator.get_state()
    print(f"오류 후 위치 유지: {state['room_name']} ({state['current_room']})")


if __name__ == "__main__":
    main()
