"""Test the backend Auto Mode mirror used by the policy evaluation."""

import unittest

from simulation import Simulator
from simulation.compare_patrol import AutoModePolicy, stale_limit_seconds


def fixed_policy(**values):
    """Return constant forecasts once every room has a reading, like the real model."""

    def forecast(simulator):
        observations = simulator.get_state()["observations"]
        ready = all(observations[room]["pm25"] is not None for room in values)
        return {"status": "ok" if ready else "initial_patrol_required",
                "predictions": dict(values) if ready else dict.fromkeys(values)}

    return AutoModePolicy(None, forecast=forecast)


def run_until(sim, policy, seconds):
    state = sim.start()
    while state["simulation_time_seconds"] < seconds:
        state = policy.tick(sim)
    return state


def arrivals(sim):
    return [(entry["time_seconds"], entry["room"])
            for entry in sim.get_history() if entry["type"] == "arrival"]


class AutoModePolicyTests(unittest.TestCase):
    def test_initial_patrol_then_forecast_move_after_stay(self):
        sim = Simulator()
        policy = fixed_policy(living_room=0.0, kitchen=40.0, bedroom=0.0)
        run_until(sim, policy, 60 * 60)
        visits = arrivals(sim)
        self.assertEqual([room for _, room in visits[:2]], ["kitchen", "bedroom"])
        self.assertEqual(visits[2][1], "kitchen")
        move = next(entry for entry in sim.get_history() if entry["type"] == "move_requested"
                    and entry["time_seconds"] > visits[1][0])
        self.assertEqual(move["time_seconds"] % 600, 0)
        self.assertGreaterEqual(move["time_seconds"] - visits[1][0], 600)
        self.assertEqual(policy.counts, {"forecast_moves": 1, "stale_revisits": 0})

    def test_stale_reading_revisit_when_no_room_qualifies(self):
        sim = Simulator()
        policy = fixed_policy(living_room=0.0, kitchen=0.0, bedroom=0.0)
        state = run_until(sim, policy, 4 * 60 * 60)
        self.assertGreaterEqual(policy.counts["stale_revisits"], 1)
        self.assertEqual(policy.counts["forecast_moves"], 0)
        ages = [reading["age_seconds"] for reading in state["observations"].values()]
        self.assertTrue(all(age is not None and age < 4 * 60 * 60 for age in ages))

    def test_stale_limit_and_day_reset(self):
        self.assertEqual(stale_limit_seconds(7), 120 * 60)
        self.assertEqual(stale_limit_seconds(8), 180 * 60)
        sim = Simulator()
        policy = fixed_policy(living_room=0.0, kitchen=0.0, bedroom=0.0)
        state = sim.start()
        while not state["finished"]:
            state = policy.tick(sim)
        sim.next_day()
        policy.tick(sim)
        self.assertEqual(policy._day, 2)
        self.assertIsNone(policy.latest_decision)


class NextDayScheduleTests(unittest.TestCase):
    def finish(self, sim):
        state = sim.start()
        while not state["finished"]:
            state = sim.step()

    def test_next_day_can_switch_to_late_dinner_and_reset_restores(self):
        sim = Simulator(seed=3)
        self.finish(sim)
        sim.next_day(late_dinner=True)
        late = Simulator(seed=3, day_index=1, late_dinner=True)
        self.assertEqual(sim.get_scenario()["events"], late.get_scenario()["events"])
        self.assertTrue(sim.get_scenario()["late_dinner"])
        self.assertEqual(len(sim.previous_days), 1)
        sim.reset()
        self.assertFalse(sim.get_scenario()["late_dinner"])
        self.assertEqual(sim.get_scenario()["events"], Simulator(seed=3).get_scenario()["events"])

    def test_invalid_late_dinner_preserves_day(self):
        sim = Simulator()
        self.finish(sim)
        with self.assertRaises(ValueError):
            sim.next_day(late_dinner="yes")
        self.assertEqual(sim.simulation_day, 1)
        self.assertTrue(sim.get_state()["finished"])


if __name__ == "__main__":
    unittest.main()
