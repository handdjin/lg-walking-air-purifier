"""python3 -m simulation.environment_demo 로 공통 환경 계산을 확인한다."""

from .environment import AirEnvironment, PollutionEvent, calculate_pm25


def main():
    print("규칙 확인: 농도 30, 오염 없음")
    print(f"자연 감소만: {calculate_pm25(30):.2f}")
    print(f"자연 감소 + 정화: {calculate_pm25(30, purifying=True):.2f}\n")

    scenario = AirEnvironment(seed=42).get_scenario()
    print("seed=42로 생성한 하루 활동 시간표 (정답 생성용)")
    for event in scenario["events"]:
        start, end = event["start_minute"], event["end_minute"]
        print(f"{event['room']:12} {event['activity']:8} "
              f"{start // 60:02}:{start % 60:02}~{end // 60:02}:{end % 60:02}")

    # 빠른 비교를 위해 시연용 요리를 00:00~00:10에 고정한다.
    # 기본 무작위 활동 시간표를 변경하는 것이 아니다.
    events = (PollutionEvent("kitchen", "cooking", 0, 10),)
    natural = AirEnvironment(events=events)
    cleaned = AirEnvironment(events=events)
    print("\n시연용 요리 00:00~00:10 / 00:10부터 주방 정화")
    print("경과 분 | 정화 없음 | 주방 정화")
    for minute in range(31):
        if minute % 5 == 0:
            a = natural.get_ground_truth()["pm25"]["kitchen"]
            b = cleaned.get_ground_truth()["pm25"]["kitchen"]
            print(f"{minute:7} | {a:9.2f} | {b:9.2f}")
        if minute < 30:
            natural.advance()
            cleaned.advance(purifying_room="kitchen" if minute >= 10 else None)
    print("\n이 비교는 정화 계산 확인용이며 자동 정화 정책이나 이동 시연은 아닙니다.")


if __name__ == "__main__":
    main()
