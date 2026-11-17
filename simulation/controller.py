"""30분 뒤 방별 예측값으로 목적지를 선택하는 초기 제어 규칙.

모델 학습이나 추론은 수행하지 않는다. 호출자가 같은 시점의 세 방 예측값을
제공한다. 실제 농도와 미래 사건 시간표는 선택에 사용하지 않는다.
"""

import math
from collections.abc import Mapping

from .house_map import HouseMap
from .pathfinding import NoPathError, find_path


def _number(value, name):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise ValueError(f"{name}은 유한한 0 이상의 숫자여야 합니다.")


def choose_destination(simulator, predictions, *, threshold=35.0,
                       travel_weight=1.0):
    """상태를 변경하지 않고 선택 결과를 반환한다.

    predictions: {방 코드: 30분 뒤 예상 PM2.5}. 세 방 모두 필요하며,
    미측정 방에 대한 예측이 없으면 호출자가 먼저 초기 순찰 등을 처리해야 한다.
    점수 = 예측 PM - 이동 분 * travel_weight. 동점은 가까운 방, 방 코드순.
    경로 예약 중에는 일시정지 여부와 관계없이 새 판단을 거부한다.
    """
    _number(threshold, "후보 기준")
    _number(travel_weight, "이동 시간 가중치")
    house = HouseMap(simulator.get_map())
    if not isinstance(predictions, Mapping) or set(predictions) != set(house.rooms):
        raise ValueError("지도에 있는 세 방의 예측값을 빠짐없이 전달하세요.")
    for room, value in predictions.items():
        _number(value, f"{room} 예측값")
    state = simulator.get_state()
    if state["finished"]:
        raise ValueError("하루가 종료되었습니다. reset() 후 판단하세요.")
    if state["remaining_steps"]:
        raise ValueError("이동 경로가 남아 있습니다. 도착한 뒤 판단하세요.")

    rooms = {}
    candidates = []
    for room in sorted(house.rooms):
        predicted = float(predictions[room])
        # 현재 방에서는 도착점까지 다시 움직이지 않고 그 위치에 머문다.
        try:
            path = ([tuple(state["position"])] if room == state["current_room"] else
                    find_path(house, state["position"], house.rooms[room].target))
        except NoPathError:
            rooms[room] = {"predicted_pm25": predicted, "reachable": False,
                           "travel_steps": None, "travel_seconds": None,
                           "score": None, "eligible": False}
            continue
        steps = len(path) - 1
        seconds = steps * state["tick_seconds"]
        score = predicted - seconds / 60 * travel_weight
        if not math.isfinite(score):
            raise ValueError("점수 계산 범위를 초과했습니다.")
        eligible = predicted >= threshold
        rooms[room] = {"predicted_pm25": predicted, "reachable": True,
                       "travel_steps": steps, "travel_seconds": seconds,
                       "score": score, "eligible": eligible}
        if eligible:
            candidates.append(room)

    target = min(candidates, key=lambda room: (
        -rooms[room]["score"], rooms[room]["travel_seconds"], room
    )) if candidates else None
    action = "wait" if target is None else (
        "stay" if target == state["current_room"] else "move")
    reason = ("all_predictions_below_threshold"
              if all(value < threshold for value in predictions.values())
              else "no_reachable_candidate") if target is None else (
                  "current_room_selected" if action == "stay" else "highest_score")
    return {"action": action, "target_room": target, "reason": reason,
            "decided_at_seconds": state["simulation_time_seconds"],
            "prediction_horizon_minutes": 30, "threshold": threshold,
            "travel_weight": travel_weight, "rooms": rooms}


def decide_and_move(simulator, predictions, *, threshold=35.0, travel_weight=1.0):
    """목적지 선택 후 다른 방이면 기존 이동 함수로 경로를 예약한다."""
    decision = choose_destination(simulator, predictions, threshold=threshold,
                                  travel_weight=travel_weight)
    if decision["action"] == "move":
        simulator.move_to(decision["target_room"])
    # start()/step()은 호출하지 않는다. 기존 실행·일시정지 상태를 유지한다.
    return {"decision": decision, "state": simulator.get_state()}
