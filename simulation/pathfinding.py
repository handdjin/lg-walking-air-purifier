"""상하좌우 이동의 최단 경로를 찾는 A*. 한 칸의 비용은 1이다."""

from heapq import heappop, heappush

from .house_map import coordinate


class NoPathError(ValueError):
    """두 이동 가능 지점 사이에 연결된 길이 없는 경우."""


def find_path(house_map, start, goal):
    """시작과 도착 칸을 모두 포함한 좌표 목록을 반환한다."""
    start, goal = coordinate(start), coordinate(goal)
    if not house_map.is_walkable(start) or not house_map.is_walkable(goal):
        raise ValueError("출발점과 목적지는 이동 가능한 칸이어야 합니다.")

    def estimate(position):
        # 대각선 이동이 없으므로 가로 거리 + 세로 거리를 사용한다.
        return abs(position[0] - goal[0]) + abs(position[1] - goal[1])

    frontier = [(estimate(start), 0, start)]
    costs = {start: 0}
    previous = {}
    while frontier:
        _, cost, current = heappop(frontier)
        if cost != costs[current]:
            continue  # 더 좋은 경로가 발견된 이후의 오래된 후보
        if current == goal:
            path = [current]
            while current in previous:
                current = previous[current]
                path.append(current)
            return list(reversed(path))
        for neighbor in house_map.neighbors(current):
            new_cost = cost + 1
            if new_cost < costs.get(neighbor, float("inf")):
                costs[neighbor] = new_cost
                previous[neighbor] = current
                heappush(frontier, (new_cost + estimate(neighbor), new_cost, neighbor))
    raise NoPathError(f"{start}에서 {goal}까지 이동할 수 있는 경로가 없습니다.")
