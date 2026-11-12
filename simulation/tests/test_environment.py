"""수식, 시간 경계, 재현성, 관측과 정답의 분리를 검증한다."""

import json
import random
import unittest

from simulation.environment import (
    AirEnvironment, PollutionEvent, calculate_pm25, generate_daily_events,
)


class FormulaTests(unittest.TestCase):
    def test_document_examples_and_order(self):
        self.assertAlmostEqual(calculate_pm25(30), 29.8)
        self.assertAlmostEqual(calculate_pm25(30, purifying=True), 28.31)
        # 20 + 3 = 23, 자연 감소 후 22.87, 정화 후 21.7265
        self.assertAlmostEqual(calculate_pm25(20, 3, True), 21.7265)

    def test_baseline_floor_and_no_instant_cleanup(self):
        self.assertEqual(calculate_pm25(10), 10)
        self.assertEqual(calculate_pm25(7), 7)
        self.assertEqual(calculate_pm25(5, purifying=True), 5)
        self.assertGreater(calculate_pm25(100, purifying=True), 5)
        value = 100
        for _ in range(1000):
            value = calculate_pm25(value, purifying=True)
        self.assertEqual(value, 5)

    def test_rejects_invalid_numbers(self):
        for value in (-1, float("nan"), float("inf"), True, "30", None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    calculate_pm25(value)
                with self.assertRaises(ValueError):
                    calculate_pm25(10, value)
        with self.assertRaises(ValueError):
            calculate_pm25(10, purifying="yes")
        with self.assertRaises(ValueError):
            calculate_pm25(1e308, 1e308)


class ScheduleTests(unittest.TestCase):
    def test_windows_durations_and_four_events(self):
        for day in range(60):
            events = generate_daily_events(seed=42, day_index=day)
            self.assertEqual(len(events), 4)
            cooking = sorted((e for e in events if e.activity == "cooking"),
                             key=lambda e: e.start_minute)
            self.assertEqual(len(cooking), 2)
            for event, lo, hi in ((cooking[0], 420, 540), (cooking[1], 1080, 1200)):
                self.assertEqual(event.room, "kitchen")
                self.assertTrue(lo <= event.start_minute <= hi)
                self.assertTrue(10 <= event.end_minute - event.start_minute <= 20)
            for activity, room, lo, hi in (("cleaning", "living_room", 780, 1020),
                                           ("bedding", "bedroom", 420, 600)):
                event, = [e for e in events if e.activity == activity]
                self.assertEqual(event.room, room)
                self.assertTrue(lo <= event.start_minute <= hi)
                self.assertTrue(5 <= event.end_minute-event.start_minute <= 10)

    def test_reproducibility_and_rng_independence(self):
        before = random.getstate()
        first = generate_daily_events(42, 3)
        self.assertEqual(random.getstate(), before)
        visitor_rng = random.Random(999)
        for _ in range(100):
            visitor_rng.choice((10, 20, 30))
        self.assertEqual(first, generate_daily_events(42, 3))
        self.assertNotEqual(first, generate_daily_events(42, 4))
        self.assertNotEqual(first, generate_daily_events(43, 3))

    def test_shifted_dinner_changes_only_dinner(self):
        normal = sorted(generate_daily_events(42), key=lambda e: (e.room, e.start_minute))
        shifted = sorted(generate_daily_events(42, late_dinner=True),
                         key=lambda e: (e.room, e.start_minute))
        for a, b in zip(normal, shifted):
            if a.room == "kitchen" and a.start_minute >= 1080:
                self.assertEqual(b.start_minute, a.start_minute+120)
                self.assertEqual(b.end_minute, a.end_minute+120)
            else:
                self.assertEqual(a, b)

    def test_invalid_schedule_inputs(self):
        for args in (("bathroom", "cooking", 1, 2), ("kitchen", "unknown", 1, 2),
                     ("kitchen", "cooking", 2, 2), ("kitchen", "cooking", -1, 2),
                     ("kitchen", "cooking", 1440, 1441)):
            with self.assertRaises(ValueError):
                PollutionEvent(*args)
        for kwargs in ({"seed": -1}, {"day_index": True}, {"late_dinner": "yes"},
                       {"events": ["bad"]}):
            with self.assertRaises(ValueError):
                AirEnvironment(**kwargs)


class EnvironmentTests(unittest.TestCase):
    def test_event_boundaries_and_time_meaning(self):
        env = AirEnvironment(events=[PollutionEvent("kitchen", "cooking", 1, 3)])
        self.assertEqual(env.advance(), 1)  # [0,1): 활동 전
        self.assertEqual(env.get_ground_truth()["pm25"]["kitchen"], 10)
        env.advance()  # [1,2): 첫 증가
        self.assertAlmostEqual(env.sample_current_room("kitchen")["pm25"], 12.97)
        env.advance()  # [2,3): 마지막 증가
        self.assertAlmostEqual(env.sample_current_room("kitchen")["pm25"], 15.9103)
        env.advance()  # [3,4): 종료 이후 자연 감소만
        self.assertAlmostEqual(env.sample_current_room("kitchen")["pm25"], 15.851197)
        self.assertEqual(env.get_ground_truth()["pm25"]["bedroom"], 10)

    def test_purification_affects_one_room_and_is_not_sticky(self):
        env = AirEnvironment(events=[])
        env.advance(purifying_room="kitchen")
        values = env.get_ground_truth()["pm25"]
        self.assertEqual(values, {"living_room": 10, "kitchen": 9.5, "bedroom": 10})
        env.advance()  # None: 정화하지 않음, 10 미만은 자연 감소 없음
        self.assertEqual(env.get_ground_truth()["pm25"], values)
        env.advance(purifying_room="bedroom")
        self.assertEqual(env.get_ground_truth()["pm25"]["bedroom"], 9.5)
        self.assertEqual(env.get_ground_truth()["pm25"]["kitchen"], 9.5)

    def test_custom_schedule_and_overlapping_emissions(self):
        events = [PollutionEvent("kitchen", "cooking", 0, 1)] * 2
        env = AirEnvironment(events=events)
        events.clear()
        env.advance()
        self.assertAlmostEqual(env.get_ground_truth()["pm25"]["kitchen"], 15.94)

    def test_full_day_repeatable_and_independent_days(self):
        first, second = AirEnvironment(seed=7), AirEnvironment(seed=7)
        first_truth = first.get_ground_truth()
        for minute in range(1440):
            purifying_room = "kitchen" if minute % 3 == 0 else None
            first.advance(purifying_room)
            second.advance(purifying_room)
            self.assertEqual(first.get_ground_truth(), second.get_ground_truth())
        self.assertEqual(first.minute, 1440)
        before = first.get_ground_truth()
        with self.assertRaises(ValueError):
            first.advance()
        self.assertEqual(first.get_ground_truth(), before)
        self.assertEqual(AirEnvironment(seed=7, day_index=1).get_ground_truth(), first_truth)

    def test_observation_has_only_one_room_and_reads_do_not_advance(self):
        env = AirEnvironment(events=[])
        self.assertEqual(env.sample_current_room("living_room"),
                         {"minute": 0, "room": "living_room", "pm25": 10})
        before = env.get_ground_truth()
        for room in (None, "bathroom", [], 1):
            with self.assertRaises(ValueError):
                env.sample_current_room(room)
        with self.assertRaises(ValueError):
            env.advance(purifying_room="bathroom")
        self.assertEqual(env.get_ground_truth(), before)

    def test_serialization_and_copy_isolation(self):
        env = AirEnvironment(seed=42)
        truth = env.get_ground_truth()
        truth["pm25"]["kitchen"] = 999
        scenario = env.get_scenario()
        scenario["events"][0]["start_minute"] = 999
        scenario["activity_rates"]["cooking"] = 999
        self.assertEqual(env.get_ground_truth()["pm25"]["kitchen"], 10)
        self.assertEqual(env.get_scenario(), AirEnvironment(seed=42).get_scenario())
        self.assertEqual(json.loads(json.dumps(env.get_scenario())), env.get_scenario())
        restored_events = [PollutionEvent(**e) for e in env.get_scenario()["events"]]
        restored = AirEnvironment(events=restored_events)
        for _ in range(1440):
            env.advance()
            restored.advance()
        self.assertEqual(env.get_ground_truth(), restored.get_ground_truth())


if __name__ == "__main__":
    unittest.main()
