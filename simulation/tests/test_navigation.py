"""표준 unittest로 경로의 최적성·안전성과 외부 연동 계약을 검증한다."""

from collections import deque
import json
import unittest

from simulation import Simulator
from simulation.house_map import HouseMap, load_house_map
from simulation.pathfinding import NoPathError, find_path


def bfs_distances(house, start):
    """A*와 독립적인 너비 우선 탐색으로 최소 이동 횟수를 구한다."""
    distances = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        for next_x, next_y in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            point = (next_x, next_y)
            if (0 <= next_x < house.width and 0 <= next_y < house.height
                    and house.grid[next_y][next_x] in ".D" and point not in distances):
                distances[point] = distances[(x, y)] + 1
                queue.append(point)
    return distances


def blocked_kitchen():
    data = load_house_map().to_dict()
    data["grid"][3] = data["grid"][3].replace("D", "#")
    return HouseMap(data)


class PathTests(unittest.TestCase):
    def test_every_walkable_pair_matches_bfs(self):
        house = load_house_map()
        points = [(x, y) for y in range(house.height) for x in range(house.width)
                  if house.is_walkable((x, y))]
        for start in points:
            distances = bfs_distances(house, start)
            self.assertEqual(len(distances), len(points))
            for goal in points:
                path = find_path(house, start, goal)
                self.assertEqual((path[0], path[-1]), (start, goal))
                self.assertEqual(len(path) - 1, distances[goal])
                for a, b in zip(path, path[1:]):
                    self.assertEqual(abs(a[0]-b[0]) + abs(a[1]-b[1]), 1)
                    self.assertTrue(house.is_walkable(b))

    def test_closed_door_makes_kitchen_unreachable(self):
        house = blocked_kitchen()
        with self.assertRaises(NoPathError):
            find_path(house, house.start, house.rooms["kitchen"].target)

    def test_invalid_endpoints(self):
        house = load_house_map()
        for point in ((0, 0), (3, 2), (-1, 0), (15, 5), (1.5, 2), (True, 2)):
            with self.subTest(point=point), self.assertRaises(ValueError):
                find_path(house, house.start, point)


class MovementTests(unittest.TestCase):
    def test_full_tour_passes_through_doors_and_stops(self):
        sim = Simulator()
        targets = {r["id"]: r["target"] for r in sim.get_map()["rooms"]}
        for room in ("kitchen", "bedroom", "living_room"):
            before = sim.get_state()["position"]
            state = sim.move_to(room)
            self.assertEqual(state["position"], before)  # 예약은 이동하지 않는다.
            seen_door = False
            count = state["remaining_steps"]
            for i in range(count):
                self.assertEqual(sim.get_state(), state)  # 조회는 움직이지 않는다.
                state = sim.step()
                self.assertEqual(sum(abs(a-b) for a, b in zip(before, state["position"])), 1)
                self.assertEqual(state["remaining_steps"], count-i-1)
                if state["current_room"] is None:
                    seen_door = True
                    self.assertIsNone(state["room_name"])
                before = state["position"]
            self.assertTrue(seen_door)
            self.assertEqual(state["position"], targets[room])
            self.assertEqual(state["current_room"], room)
            self.assertEqual(state["destination"], room)
            self.assertEqual(state["status"], "idle")
            self.assertEqual(sim.step(), state)

    def test_manual_redirect_from_door(self):
        sim = Simulator()
        sim.move_to("kitchen")
        while sim.get_state()["current_room"] is not None:
            sim.step()
        position = sim.get_state()["position"]
        state = sim.move_to("bedroom")
        self.assertEqual(state["position"], position)
        for _ in range(state["remaining_steps"]):
            state = sim.step()
        self.assertEqual(state["current_room"], "bedroom")
        self.assertEqual(state["position"], [11, 8])

    def test_invalid_request_preserves_in_progress_route(self):
        sim = Simulator()
        sim.move_to("kitchen")
        sim.step()
        before = sim.get_state()
        for room in ("bathroom", "", None, [], 123):
            with self.assertRaises(ValueError):
                sim.move_to(room)
            self.assertEqual(sim.get_state(), before)

    def test_unreachable_request_preserves_in_progress_route(self):
        sim = Simulator(blocked_kitchen())
        sim.move_to("bedroom")
        sim.step()
        before = sim.get_state()
        with self.assertRaises(NoPathError):
            sim.move_to("kitchen")
        self.assertEqual(sim.get_state(), before)

    def test_same_destination_and_return_to_start(self):
        sim = Simulator()
        state = sim.move_to("living_room")
        self.assertEqual(state["remaining_steps"], 0)
        self.assertEqual(state["status"], "idle")
        state = sim.move_to("kitchen")
        self.assertEqual(sim.move_to("kitchen"), state)
        sim.step()
        state = sim.move_to("living_room")
        for _ in range(state["remaining_steps"]):
            state = sim.step()
        self.assertEqual(state["position"], [2, 4])

    def test_json_and_returned_data_are_independent(self):
        sim = Simulator()
        sim.move_to("bedroom")
        before = sim.get_state()
        self.assertEqual(json.loads(json.dumps(before)), before)
        self.assertEqual(json.loads(json.dumps(sim.get_map())), sim.get_map())
        state = sim.get_state()
        state["position"][0] = 999
        state["remaining_path"][0][0] = 999
        data = sim.get_map()
        data["rooms"][0]["target"][0] = 999
        data["grid"][0] = "broken"
        self.assertEqual(sim.get_state(), before)
        self.assertEqual(sim.get_map()["rooms"][0]["target"], [2, 4])
        self.assertEqual(Simulator().get_state()["position"], [2, 4])


class MapTests(unittest.TestCase):
    def test_rejects_bad_map_data(self):
        for change in ("width", "symbol", "target", "overlap", "start"):
            data = load_house_map().to_dict()
            if change == "width":
                data["grid"][0] = "#"
            elif change == "symbol":
                data["grid"][0] = "?" + data["grid"][0][1:]
            elif change == "target":
                data["rooms"][0]["target"] = [3, 2]
            elif change == "overlap":
                data["rooms"][1]["bounds"] = [1, 1, 13, 4]
            else:
                data["start"] = [0, 0]
            with self.subTest(change=change), self.assertRaises(ValueError):
                HouseMap(data)


if __name__ == "__main__":
    unittest.main()
