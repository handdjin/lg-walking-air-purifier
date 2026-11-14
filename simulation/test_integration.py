"""실제 이동과 시간·관측·정화 제어를 함께 검증한다."""

import json
import unittest

from simulation import Simulator
from simulation.environment import AirEnvironment, PollutionEvent, calculate_pm25


def run_seconds(sim, seconds):
    tick = sim.get_state()["tick_seconds"]
    assert seconds % tick == 0
    for _ in range(seconds // tick):
        sim.step()
    return sim.get_state()


def arrive(sim, room):
    state = sim.move_to(room)
    for _ in range(state["remaining_steps"]):
        state = sim.step()
    return state


class IntegratedTests(unittest.TestCase):
    def test_initial_observation_and_pause_start_idempotence(self):
        sim = Simulator(events=[])
        state = sim.get_state()
        self.assertFalse(state["is_running"])
        self.assertEqual(state["observations"]["living_room"]["pm25"], 10)
        self.assertIsNone(state["observations"]["kitchen"]["pm25"])
        self.assertIsNone(state["observations"]["bedroom"]["measured_at_seconds"])
        self.assertEqual(sim.step(), state)
        sim.move_to("kitchen")
        before = sim.get_state()
        self.assertEqual(sim.step(), before)  # 경로만 예약해도 시작 전에는 안 움직인다.
        sim.start()
        history = sim.get_history()
        sim.start()
        self.assertEqual(history, sim.get_history())
        sim.step()
        sim.pause()
        paused = sim.get_state()
        truth = sim.get_ground_truth()
        run_seconds(sim, 600)
        self.assertEqual(sim.get_state(), paused)
        self.assertEqual(sim.get_ground_truth(), truth)
        sim.start()
        state = sim.step()
        self.assertEqual(state["simulation_time_seconds"], 20)

    def test_time_continues_without_path_and_environment_updates_on_minute(self):
        sim = Simulator(events=[PollutionEvent("kitchen", "cooking", 0, 2)])
        sim.start()
        state = run_seconds(sim, 50)
        self.assertEqual(state["simulation_time_seconds"], 50)
        self.assertEqual(sim.get_ground_truth()["pm25"]["kitchen"], 10)
        state = sim.step()
        self.assertEqual(state["environment_minute"], 1)
        self.assertAlmostEqual(sim.get_ground_truth()["pm25"]["kitchen"], 12.97)
        self.assertEqual(state["position"], [2, 4])
        self.assertIsNone(state["observations"]["kitchen"]["pm25"])
        self.assertNotIn("events", state)
        self.assertNotIn("true_pm25", state)

    def test_arrival_periodic_observation_and_other_rooms_stay_stale(self):
        sim = Simulator(events=[])
        sim.start()
        state = arrive(sim, "kitchen")
        self.assertEqual(state["simulation_time_seconds"], 100)
        observed = state["observations"]["kitchen"]
        self.assertEqual(observed["measured_at_seconds"], 100)
        self.assertEqual(observed["source_minute"], 1)
        self.assertEqual(state["observations"]["living_room"]["age_seconds"], 100)
        # 분 중간에도 측정 시각과 환경의 마지막 갱신 시각을 구분한다.
        run_seconds(sim, 590)
        self.assertEqual(sim.get_state()["observations"]["kitchen"]["measured_at_seconds"], 100)
        state = sim.step()
        self.assertEqual(state["observations"]["kitchen"]["measured_at_seconds"], 700)
        measurements = [e for e in sim.get_history() if e["type"] == "measurement"]
        self.assertEqual([(e["room"], e["time_seconds"]) for e in measurements],
                         [("living_room", 0), ("kitchen", 100), ("kitchen", 700)])
        self.assertEqual(state["observations"]["living_room"]["measured_at_seconds"], 0)
        self.assertIsNone(state["observations"]["bedroom"]["pm25"])

    def test_door_and_transit_do_not_measure_and_invalid_move_is_atomic(self):
        sim = Simulator(events=[])
        sim.start()
        sim.move_to("kitchen")
        while sim.get_state()["current_room"] is not None:
            sim.step()
        state = sim.get_state()
        self.assertEqual(len([e for e in sim.get_history() if e["type"] == "measurement"]), 1)
        self.assertFalse(state["is_purifying"])
        history = sim.get_history()
        with self.assertRaises(ValueError):
            sim.move_to("bathroom")
        self.assertEqual(state, sim.get_state())
        self.assertEqual(history, sim.get_history())
        arrive(sim, "bedroom")
        self.assertIsNone(sim.get_state()["observations"]["kitchen"]["pm25"])

    def test_duplicate_arrival_and_periodic_measurement_are_deduplicated(self):
        sim = Simulator(events=[])
        sim.move_to("living_room")
        self.assertEqual(len([e for e in sim.get_history() if e["type"] == "measurement"]), 1)
        sim.start()
        run_seconds(sim, 600)
        count = len([e for e in sim.get_history() if e["type"] == "measurement"])
        sim.move_to("living_room")
        self.assertEqual(len([e for e in sim.get_history() if e["type"] == "measurement"]), count)

    def test_automatic_on_off_only_from_measurements(self):
        sim = Simulator(events=[PollutionEvent("living_room", "cleaning", 0, 20)])
        sim.start()
        run_seconds(sim, 600)
        self.assertFalse(sim.get_state()["is_purifying"])  # 10분 측정은 35 미만
        state = run_seconds(sim, 600)
        self.assertGreaterEqual(state["observations"]["living_room"]["pm25"], 35)
        self.assertEqual(state["status"], "purifying")
        self.assertTrue(state["is_purifying"])
        before = sim.get_ground_truth()["pm25"]["living_room"]
        run_seconds(sim, 60)
        self.assertAlmostEqual(sim.get_ground_truth()["pm25"]["living_room"],
                               calculate_pm25(before, purifying=True))
        # 실제 농도가 내려가도 다음 측정 전에는 판단을 바꾸지 않는다.
        state = run_seconds(sim, 9 * 60)
        self.assertGreater(state["observations"]["living_room"]["pm25"], 15)
        self.assertTrue(state["is_purifying"])
        state = run_seconds(sim, 10 * 60)
        self.assertLessEqual(state["observations"]["living_room"]["pm25"], 15)
        self.assertFalse(state["is_purifying"])
        self.assertEqual(state["status"], "idle")

    def test_partial_minute_and_no_purification_during_movement(self):
        events = [PollutionEvent("kitchen", "cooking", 0, 20)]
        sim, reference = Simulator(events=events), AirEnvironment(events=events)
        sim.start()
        run_seconds(sim, 600)
        state = arrive(sim, "kitchen")  # 700초에 도착. 환경은 660초까지 갱신된 상태.
        self.assertTrue(state["is_purifying"])
        for _ in range(11):
            reference.advance()
        self.assertEqual(sim.get_ground_truth(), reference.get_ground_truth())
        run_seconds(sim, 20)  # 700~720초의 20초 동안만 정화
        reference.advance(purification_seconds={"kitchen": 20})
        self.assertEqual(sim.get_ground_truth(), reference.get_ground_truth())
        sim.step()  # 720~730초의 10초 정화
        sim.move_to("bedroom")
        self.assertFalse(sim.get_state()["is_purifying"])
        run_seconds(sim, 50)  # 730~780초는 이동만
        reference.advance(purification_seconds={"kitchen": 10})
        self.assertEqual(sim.get_ground_truth(), reference.get_ground_truth())
        run_seconds(sim, 60)  # 780~840초도 이동만
        reference.advance()
        self.assertEqual(sim.get_ground_truth(), reference.get_ground_truth())

    def test_pause_mid_minute_and_reset_preserve_c_reset_behavior(self):
        events = [PollutionEvent("living_room", "cleaning", 0, 20)]
        sim = Simulator(events=events)
        initial, scenario = sim.get_state(), sim.get_scenario()
        sim.start()
        run_seconds(sim, 1210)  # 정화 시작 후 10초
        sim.pause()
        self.assertFalse(sim.get_state()["is_purifying"])
        self.assertEqual(sim.get_state()["status"], "purifying")  # 재개할 동작 보존
        truth = sim.get_ground_truth()
        run_seconds(sim, 600)
        self.assertEqual(sim.get_ground_truth(), truth)
        sim.start()
        run_seconds(sim, 50)
        self.assertAlmostEqual(sim.get_ground_truth()["pm25"]["living_room"],
                               calculate_pm25(truth["pm25"]["living_room"], purifying=True))
        sim.move_to("kitchen")
        sim.step()
        self.assertEqual(sim.reset(), initial)
        self.assertEqual(sim.get_scenario(), scenario)
        self.assertEqual(sim.get_ground_truth()["pm25"],
                         {"living_room": 10, "kitchen": 10, "bedroom": 10})
        self.assertEqual([e["type"] for e in sim.get_history()], ["reset", "measurement"])
        self.assertEqual(sim.step(), initial)
        sim.start()
        run_seconds(sim, 60)
        self.assertAlmostEqual(sim.get_ground_truth()["pm25"]["living_room"], 11.98)

    def test_reset_replays_same_seed_and_actions(self):
        sim = Simulator(seed=42)
        def play():
            sim.start()
            arrive(sim, "kitchen")
            run_seconds(sim, 600)
            return sim.get_state(), sim.get_history(), sim.get_ground_truth()
        first = play()
        sim.reset()
        self.assertEqual(play(), first)

    def test_end_of_day_and_configurable_tick(self):
        sim = Simulator(events=[], tick_seconds=60)
        sim.start()
        state = run_seconds(sim, 86400)
        self.assertTrue(state["finished"])
        self.assertFalse(state["is_running"])
        self.assertEqual(sim.step(), state)
        with self.assertRaises(ValueError):
            sim.start()
        with self.assertRaises(ValueError):
            sim.move_to("kitchen")
        sim.reset()
        self.assertFalse(sim.get_state()["finished"])
        for tick in (0, -1, 7, 61, True, 10.0):
            with self.assertRaises(ValueError):
                Simulator(tick_seconds=tick)

    def test_public_state_and_history_are_json_copies(self):
        sim = Simulator(events=[])
        state = sim.get_state()
        self.assertEqual(json.loads(json.dumps(state)), state)
        state["observations"]["living_room"]["pm25"] = 999
        history = sim.get_history()
        history[1]["pm25"] = 999
        self.assertEqual(sim.get_state()["observations"]["living_room"]["pm25"], 10)
        self.assertEqual(sim.get_history()[1]["pm25"], 10)


class PartialEnvironmentTests(unittest.TestCase):
    def test_old_api_unchanged_and_partial_formula(self):
        self.assertAlmostEqual(calculate_pm25(30, purifying=True), 28.31)
        self.assertAlmostEqual(calculate_pm25(30, purifying=True, purifying_seconds=30),
                               29.8 * 0.95 ** 0.5)
        self.assertEqual(calculate_pm25(30, purifying=True, purifying_seconds=0), 29.8)
        env = AirEnvironment(events=[])
        env.advance(purification_seconds={"living_room": 20, "kitchen": 30})
        self.assertAlmostEqual(env.get_ground_truth()["pm25"]["living_room"], 10 * .95 ** (20/60))
        self.assertAlmostEqual(env.get_ground_truth()["pm25"]["kitchen"], 10 * .95 ** .5)
        self.assertEqual(env.get_ground_truth()["pm25"]["bedroom"], 10)

    def test_invalid_exposure_does_not_advance(self):
        env = AirEnvironment(events=[])
        for exposure in ({"kitchen": 61}, {"kitchen": -1}, {"kitchen": float("nan")},
                         {"kitchen": True}, {"bedroom": 40, "kitchen": 30}, {"bad": 10}, []):
            with self.subTest(exposure=exposure), self.assertRaises(ValueError):
                env.advance(purification_seconds=exposure)
            self.assertEqual(env.minute, 0)
        with self.assertRaises(ValueError):
            env.advance("kitchen", purification_seconds={"kitchen": 10})
        self.assertEqual(env.minute, 0)


if __name__ == "__main__":
    unittest.main()
