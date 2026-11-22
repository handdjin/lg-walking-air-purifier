"""A* shortest paths on a four-connected grid with unit movement cost."""

from heapq import heappop, heappush

from .house_map import coordinate


class NoPathError(ValueError):
    """Raised when two walkable points are disconnected."""


def find_path(house_map, start, goal):
    """Return the path coordinates, including the start and goal."""
    start, goal = coordinate(start), coordinate(goal)
    if not house_map.is_walkable(start) or not house_map.is_walkable(goal):
        raise ValueError("Start and goal must both be walkable cells.")

    def estimate(position):
        # Use Manhattan distance because diagonal movement is unavailable.
        return abs(position[0] - goal[0]) + abs(position[1] - goal[1])

    frontier = [(estimate(start), 0, start)]
    costs = {start: 0}
    previous = {}
    while frontier:
        _, cost, current = heappop(frontier)
        if cost != costs[current]:
            continue  # Skip an outdated candidate after finding a better route
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
    raise NoPathError(f"{start} has no walkable route to {goal}.")
