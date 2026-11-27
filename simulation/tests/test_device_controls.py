"""Test device controls: stop/start operation and return to the dock."""

import unittest

from simulation import Simulator
from simulation.compare_patrol import AutoModePolicy
from simulation.environment import PollutionEvent
from simulation.house_map import HouseMap, load_house_map


def run_steps(sim, count):
    state = sim.get_state()
    for _ in range(count):
        state = sim.step()
    return state


def history_types(sim):
    return [entry["type"] for entry in sim.get_history()]


class StopStartTests(unittest.TestCase):
    def test_stop_keeps_time_and_pollution_but_not_movement(self):
        events = [PollutionEvent("living_room", "cleaning", 0, 30)]
        sim = Simulator(events=events)
        sim.start()
        sim.move_to("kitchen")
        sim.step()
        stopped = sim.stop_operation()
        self.assertEqual(stopped["device_state"], "stopped")
        self.assertEqual(stopped["status"], "idle")
        before_truth = sim.get_ground_truth()["pm25"]["living_room"]
        state = run_steps(sim, 18)  # Three simulated minutes
        self.assertEqual(state["position"], stopped["position"])
        self.assertEqual(state["remaining_path"], stopped["remaining_path"])
        self.assertEqual(state["simulation_time_seconds"],
                         stopped["simulation_time_seconds"] + 180)
        self.assertGreater(sim.get_ground_truth()["pm25"]["living_room"], before_truth)
        with self.assertRaises(ValueError):
            sim.move_to("bedroom")
        resumed = sim.start_operation()
        self.assertEqual(resumed["device_state"], "running")
        state = run_steps(sim, resumed["remaining_steps"])
        self.assertEqual((state["current_room"], state["position"]), ("kitchen", [11, 3]))

    def test_stop_turns_off_purification_and_skips_measurements(self):
        sim = Simulator(events=[PollutionEvent("living_room", "cleaning", 0, 20)])
        sim.start()
        state = run_steps(sim, 6 * 15)  # 15 minutes: periodic reading turns purification on
        self.assertTrue(state["is_purifying"])
        state = sim.stop_operation()
        self.assertFalse(state["is_purifying"])
        self.assertIn("purification_off", history_types(sim))
        readings = history_types(sim).count("measurement")
        run_steps(sim, 6 * 30)
        self.assertEqual(history_types(sim).count("measurement"), readings)
        sim.start_operation()
        self.assertEqual(history_types(sim).count("measurement"), readings + 1)
        last = [entry for entry in sim.get_history() if entry["type"] == "measurement"][-1]
        self.assertEqual(last["reason"], "operation_started")

    def test_stop_and_start_are_idempotent(self):
        sim = Simulator()
        self.assertEqual(sim.start_operation(), sim.get_state())
        sim.stop_operation()
        count = len(sim.get_history())
        sim.stop_operation()
        self.assertEqual(len(sim.get_history()), count)


class DockTests(unittest.TestCase):
    def test_return_to_dock_then_wait_until_started(self):
        sim = Simulator()
        sim.start()
        sim.move_to("bedroom")
        run_steps(sim, sim.get_state()["remaining_steps"])
        state = sim.return_to_dock()
        self.assertEqual(state["device_state"], "returning")
        self.assertIsNone(state["destination"])
        self.assertFalse(state["is_purifying"])
        state = run_steps(sim, state["remaining_steps"])
        self.assertEqual(state["device_state"], "docked")
        self.assertEqual(state["position"], state["dock"])
        self.assertEqual(state["dock"], [1, 9])
        self.assertIn("docked", history_types(sim))
        readings = history_types(sim).count("measurement")
        state = run_steps(sim, 6 * 30)
        self.assertEqual(state["position"], [1, 9])
        self.assertEqual(history_types(sim).count("measurement"), readings)
        with self.assertRaises(ValueError):
            sim.move_to("kitchen")
        state = sim.start_operation()
        self.assertEqual(state["device_state"], "running")
        self.assertEqual(sim.move_to("kitchen")["device_state"], "running")

    def test_return_when_already_at_dock_and_when_stopped(self):
        sim = Simulator()
        sim.start()
        state = sim.return_to_dock()
        state = run_steps(sim, state["remaining_steps"])
        self.assertEqual(state["device_state"], "docked")
        count = len(sim.get_history())
        self.assertEqual(sim.return_to_dock()["device_state"], "docked")
        self.assertEqual(len(sim.get_history()), count)
        sim.start_operation()
        sim.move_to("kitchen")
        sim.step()
        sim.stop_operation()
        state = sim.return_to_dock()
        self.assertEqual(state["device_state"], "returning")
        state = run_steps(sim, state["remaining_steps"])
        self.assertEqual((state["device_state"], state["position"]), ("docked", [1, 9]))

    def test_move_request_cancels_return(self):
        sim = Simulator()
        sim.start()
        sim.move_to("kitchen")
        run_steps(sim, sim.get_state()["remaining_steps"])
        sim.return_to_dock()
        sim.step()
        state = sim.move_to("bedroom")
        self.assertEqual(state["device_state"], "running")
        state = run_steps(sim, state["remaining_steps"])
        self.assertEqual((state["current_room"], state["device_state"]), ("bedroom", "running"))

    def test_blocked_route_to_dock_stops_return(self):
        sim = Simulator()
        sim.start()
        sim.move_to("kitchen")
        run_steps(sim, sim.get_state()["remaining_steps"])
        sim.return_to_dock()
        state = sim.set_blocked([(7, 3)])
        self.assertEqual((state["device_state"], state["remaining_steps"]), ("running", 0))
        self.assertIn("route_blocked", history_types(sim))
        with self.assertRaises(ValueError):
            sim.set_blocked([(2, 4)])

    def test_reset_and_next_day_start_running_at_dock(self):
        sim = Simulator()
        sim.stop_operation()
        self.assertEqual(sim.reset()["device_state"], "running")
        sim.return_to_dock()
        state = sim.start()
        while not state["finished"]:
            state = sim.step()
        self.assertEqual(sim.next_day()["device_state"], "running")


class DockMapTests(unittest.TestCase):
    def test_dock_is_a_separate_living_room_corner(self):
        house = load_house_map()
        self.assertEqual(house.dock, (1, 9))
        self.assertEqual(house.room_at(house.dock), "living_room")
        self.assertNotEqual(house.dock, house.start)
        self.assertNotIn(house.dock, {room.target for room in house.rooms.values()})
        self.assertEqual(Simulator().get_map()["dock"], [1, 9])
        self.assertEqual(Simulator().get_state()["position"], [2, 4])  # Days still start at [2, 4]

    def test_dock_defaults_to_start_and_rejects_bad_cells(self):
        data = load_house_map().to_dict()
        del data["dock"]
        self.assertEqual(HouseMap(data).dock, (2, 4))
        for dock in ([0, 0], [3, 2], [7, 3], [1.5, 2]):
            with self.subTest(dock=dock), self.assertRaises(ValueError):
                HouseMap({**data, "dock": dock})


class AutoModeDeviceTests(unittest.TestCase):
    def test_auto_mode_makes_no_moves_while_docked(self):
        def forecast(simulator):
            observations = simulator.get_state()["observations"]
            ready = all(reading["pm25"] is not None for reading in observations.values())
            values = {"living_room": 0.0, "kitchen": 90.0, "bedroom": 0.0}
            return {"status": "ok" if ready else "initial_patrol_required",
                    "predictions": values if ready else dict.fromkeys(values)}

        sim = Simulator()
        policy = AutoModePolicy(None, forecast=forecast)
        sim.return_to_dock()
        state = sim.start()
        for _ in range(6 * 60):
            state = policy.tick(sim)
        self.assertEqual((state["device_state"], state["position"]), ("docked", [1, 9]))
        self.assertNotIn("move_requested", history_types(sim))
        sim.start_operation()
        for _ in range(6 * 20):
            state = policy.tick(sim)
        self.assertIn("move_requested", history_types(sim))


if __name__ == "__main__":
    unittest.main()
