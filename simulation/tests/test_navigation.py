"""Use unittest to check path optimality, safety, and the external interface."""

from collections import deque
import json
import unittest

from simulation import Simulator
from simulation.house_map import HouseMap, load_house_map
from simulation.pathfinding import DStarLite, NoPathError, find_path


def bfs_distances(house, start):
    """Planner-independent breadth-first search gives the minimum number of steps."""
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


class DStarLiteReplanningTests(unittest.TestCase):
    """Incremental replanning must match a fresh search on the changed grid."""

    def test_closing_kitchen_door_after_planning(self):
        house = load_house_map()
        planner = DStarLite(house, house.start, house.rooms["kitchen"].target)
        self.assertIn((7, 3), planner.path())
        planner.update_cells(blocked=[(7, 3)])
        with self.assertRaises(NoPathError):
            planner.path()
        planner.update_cells(cleared=[(7, 3)])
        self.assertEqual(len(planner.path()) - 1,
                         bfs_distances(house, house.start)[house.rooms["kitchen"].target])

    def test_replans_from_new_start_around_new_obstacle(self):
        house = load_house_map()
        goal = house.rooms["bedroom"].target
        planner = DStarLite(house, house.start, goal)
        route = planner.path()
        planner.move_start(route[3])
        blocked = route[5]
        planner.update_cells(blocked=[blocked])
        replanned = planner.path()
        self.assertEqual((replanned[0], replanned[-1]), (route[3], goal))
        self.assertNotIn(blocked, replanned)
        data = house.to_dict()
        row = data["grid"][blocked[1]]
        data["grid"][blocked[1]] = row[:blocked[0]] + "X" + row[blocked[0] + 1:]
        fresh = find_path(HouseMap(data), route[3], goal)
        self.assertEqual(len(replanned), len(fresh))

    def test_rejects_blocking_goal_and_blocked_start(self):
        house = load_house_map()
        goal = house.rooms["kitchen"].target
        planner = DStarLite(house, house.start, goal)
        with self.assertRaises(ValueError):
            planner.update_cells(blocked=[goal])
        planner.update_cells(blocked=[(3, 4)])
        with self.assertRaises(ValueError):
            planner.move_start((3, 4))


def with_obstacles(house, cells):
    data = house.to_dict()
    for x, y in cells:
        row = data["grid"][y]
        data["grid"][y] = row[:x] + "X" + row[x + 1:]
    return HouseMap(data)


def run_route(sim):
    state = sim.get_state()
    while state["remaining_steps"]:
        state = sim.step()
    return state


class SimulatorReplanningTests(unittest.TestCase):
    """Run-time blocked cells trigger D* Lite replanning inside Simulator."""

    def test_no_blocked_cells_by_default(self):
        sim = Simulator()
        self.assertEqual(sim.get_state()["blocked_cells"], [])
        self.assertEqual(sim.move_to("kitchen")["blocked_cells"], [])

    def test_blocking_remaining_route_replans_around_cell(self):
        sim = Simulator()
        sim.start()
        sim.move_to("bedroom")
        sim.step()
        state = sim.get_state()
        cell = tuple(state["remaining_path"][2])
        self.assertNotEqual(cell, (7, 8))  # A living-room cell with a detour available
        state = sim.set_blocked([cell])
        self.assertEqual(state["blocked_cells"], [list(cell)])
        self.assertNotIn(list(cell), state["remaining_path"])
        expected = find_path(with_obstacles(load_house_map(), [cell]),
                             tuple(state["position"]), (11, 8))
        self.assertEqual(state["remaining_steps"], len(expected) - 1)
        self.assertEqual(sim.get_history()[-1]["type"], "replanned")
        previous = state["position"]
        for _ in range(state["remaining_steps"]):
            state = sim.step()
            self.assertEqual(sum(abs(a - b) for a, b in zip(previous, state["position"])), 1)
            self.assertNotEqual(tuple(state["position"]), cell)
            previous = state["position"]
        self.assertEqual((state["current_room"], state["position"]), ("bedroom", [11, 8]))

    def test_closed_door_stops_route_and_reopening_restores_it(self):
        sim = Simulator()
        sim.start()
        sim.move_to("kitchen")
        sim.step()
        state = sim.set_blocked([(7, 3)])
        self.assertEqual(state["remaining_steps"], 0)
        self.assertNotEqual(state["status"], "moving")
        self.assertEqual(state["destination"], "kitchen")
        self.assertIn("route_blocked", [entry["type"] for entry in sim.get_history()])
        position = state["position"]
        self.assertEqual(sim.step()["position"], position)  # Stays put after stopping
        before = sim.get_state()
        with self.assertRaises(NoPathError):
            sim.move_to("kitchen")
        with self.assertRaises(NoPathError):
            sim.estimate_travel_seconds("kitchen")
        self.assertEqual(sim.get_state(), before)
        sim.set_blocked([(7, 3)], blocked=False)
        sim.move_to("kitchen")
        state = run_route(sim)
        self.assertEqual((state["current_room"], state["position"]), ("kitchen", [11, 3]))
        self.assertEqual(state["blocked_cells"], [])

    def test_reopening_cell_shortens_active_route(self):
        sim = Simulator()
        sim.set_blocked([(4, 4), (4, 3)])  # Force a detour around the direct cells
        long_route = sim.move_to("kitchen")["remaining_steps"]
        state = sim.set_blocked([(4, 4), (4, 3)], blocked=False)
        self.assertEqual(state["remaining_steps"], 10)
        self.assertGreater(long_route, 10)
        self.assertEqual(sim.get_history()[-1]["type"], "replanned")

    def test_invalid_blocking_preserves_state(self):
        sim = Simulator()
        sim.move_to("kitchen")
        before = sim.get_state()
        for cells in ([(0, 0)], [(3, 2)], [(-1, 4)], [(11, 3)], [(2, 4)], [(4, 4), (0, 0)],
                      [(1.5, 2)], ["ab"]):
            with self.subTest(cells=cells), self.assertRaises(ValueError):
                sim.set_blocked(cells)
            self.assertEqual(sim.get_state(), before)
        with self.assertRaises(ValueError):
            sim.set_blocked([(4, 4)], blocked="yes")
        self.assertEqual(sim.set_blocked([(4, 4)], blocked=False), before)  # Not blocked: no-op

    def test_controller_and_reset_respect_blocked_cells(self):
        from simulation.controller import choose_destination
        sim = Simulator()
        sim.set_blocked([(7, 3)])
        decision = choose_destination(
            sim, {"living_room": 0.0, "kitchen": 90.0, "bedroom": 40.0}, threshold=20)
        self.assertFalse(decision["rooms"]["kitchen"]["reachable"])
        self.assertEqual(decision["target_room"], "bedroom")
        self.assertEqual(sim.reset()["blocked_cells"], [])


class MovementTests(unittest.TestCase):
    def test_full_tour_passes_through_doors_and_stops(self):
        sim = Simulator()
        sim.start()
        targets = {r["id"]: r["target"] for r in sim.get_map()["rooms"]}
        for room in ("kitchen", "bedroom", "living_room"):
            before = sim.get_state()["position"]
            state = sim.move_to(room)
            self.assertEqual(state["position"], before)  # Reserving a route does not move the purifier.
            seen_door = False
            count = state["remaining_steps"]
            for i in range(count):
                self.assertEqual(sim.get_state(), state)  # Reading state does not move the purifier.
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
            paused = sim.pause()
            self.assertEqual(sim.step(), paused)
            sim.start()

    def test_manual_redirect_from_door(self):
        sim = Simulator()
        sim.start()
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
        sim.start()
        sim.move_to("kitchen")
        sim.step()
        before = sim.get_state()
        for room in ("bathroom", "", None, [], 123):
            with self.assertRaises(ValueError):
                sim.move_to(room)
            self.assertEqual(sim.get_state(), before)

    def test_unreachable_request_preserves_in_progress_route(self):
        sim = Simulator(blocked_kitchen())
        sim.start()
        sim.move_to("bedroom")
        sim.step()
        before = sim.get_state()
        with self.assertRaises(NoPathError):
            sim.move_to("kitchen")
        self.assertEqual(sim.get_state(), before)

    def test_same_destination_and_return_to_start(self):
        sim = Simulator()
        sim.start()
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
        sim.start()
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
