"""예측 입력·경로 비용·판단의 상태 보존과 실제 이동 연결 검증."""

import json
import unittest
from unittest.mock import patch

from simulation import Simulator
from simulation.controller import choose_destination, decide_and_move
from simulation.house_map import HouseMap, load_house_map


def values(living=20, kitchen=60, bedroom=40):
    return dict(living_room=living, kitchen=kitchen, bedroom=bedroom)


class ControllerTests(unittest.TestCase):
    def test_select_and_arrive_without_implicit_start(self):
        sim = Simulator(events=())
        result = decide_and_move(sim, values())
        self.assertEqual(result['decision']['target_room'], 'kitchen')
        self.assertEqual(result['decision']['rooms']['kitchen']['travel_seconds'], 100)
        self.assertFalse(result['state']['is_running'])
        self.assertEqual(result['state']['position'], [2, 4])
        sim.start()
        for _ in range(result['state']['remaining_steps']):
            sim.step()
        state = sim.get_state()
        self.assertEqual(state['current_room'], 'kitchen')
        self.assertEqual(state['simulation_time_seconds'], 100)
        self.assertEqual(state['observations']['kitchen']['measured_at_seconds'], 100)
        self.assertFalse(state['is_purifying'])  # 높은 예측만으로 정화하지 않음

    def test_changed_predictions_change_destination(self):
        sim = Simulator(events=())
        self.assertEqual(choose_destination(sim, values())['target_room'], 'kitchen')
        self.assertEqual(choose_destination(sim, values(20, 40, 60))['target_room'], 'bedroom')

    def test_travel_penalty_can_outweigh_slightly_higher_pm(self):
        sim = Simulator(events=())
        pred = values(50, 51, 20)
        self.assertEqual(choose_destination(sim, pred)['target_room'], 'living_room')
        self.assertEqual(choose_destination(sim, pred, travel_weight=0)['target_room'], 'kitchen')

    def test_score_tie_prefers_nearer_room(self):
        sim = Simulator(events=())
        self.assertEqual(choose_destination(sim, values(50, 60, 20),
                                           travel_weight=6)['target_room'], 'living_room')

    def test_threshold_and_current_room_do_not_change_state(self):
        sim = Simulator(events=())
        initial = sim.get_state(), sim.get_history()
        decision = decide_and_move(sim, values(35, 20, 20))['decision']
        self.assertEqual(decision['action'], 'stay')
        self.assertEqual((sim.get_state(), sim.get_history()), initial)
        decision = decide_and_move(sim, values(34.99, 10, 20))['decision']
        self.assertEqual(decision['action'], 'wait')
        self.assertEqual(decision['reason'], 'all_predictions_below_threshold')
        self.assertEqual((sim.get_state(), sim.get_history()), initial)

    def test_unreachable_candidate_skipped_or_wait(self):
        data = load_house_map().to_dict()
        data['grid'][3] = data['grid'][3].replace('D', '#')
        sim = Simulator(HouseMap(data), events=())
        result = choose_destination(sim, values(20, 100, 40))
        self.assertFalse(result['rooms']['kitchen']['reachable'])
        self.assertEqual(result['target_room'], 'bedroom')
        initial = sim.get_state()
        result = decide_and_move(sim, values(20, 100, 20))
        self.assertEqual(result['decision']['reason'], 'no_reachable_candidate')
        self.assertEqual(sim.get_state(), initial)

    def test_invalid_inputs_preserve_all_state(self):
        sim = Simulator(events=())
        initial = sim.get_state(), sim.get_history(), sim.get_ground_truth()
        bad = [None, {}, {'kitchen': 40}, {**values(), 'bathroom': 50}]
        bad.extend(values(kitchen=v) for v in [None, True, '50', -1, float('nan'), float('inf')])
        for predictions in bad:
            with self.subTest(predictions=predictions), self.assertRaises(ValueError):
                decide_and_move(sim, predictions)
            self.assertEqual((sim.get_state(), sim.get_history(), sim.get_ground_truth()), initial)
        for setting in [{'threshold': -1}, {'travel_weight': float('nan')}, {'threshold': True}]:
            with self.assertRaises(ValueError):
                decide_and_move(sim, values(), **setting)

    def test_reserved_or_active_path_not_overridden(self):
        sim = Simulator(events=())
        sim.move_to('kitchen')
        for running in [False, True]:
            if running:
                sim.start()
                sim.step()
            initial = sim.get_state(), sim.get_history()
            with self.assertRaises(ValueError):
                decide_and_move(sim, values(20, 20, 100))
            self.assertEqual((sim.get_state(), sim.get_history()), initial)

    def test_day_end_rejected(self):
        sim = Simulator(events=(), tick_seconds=60)
        sim.start()
        for _ in range(1440):
            sim.step()
        with self.assertRaises(ValueError):
            decide_and_move(sim, values())

    def test_no_hidden_truth_and_json_independent_result(self):
        sim = Simulator(events=(), tick_seconds=20)
        before = sim.get_state()
        with patch.object(sim, 'get_ground_truth', side_effect=AssertionError('hidden truth')), \
                patch.object(sim, 'get_scenario', side_effect=AssertionError('future events')):
            result = choose_destination(sim, values())
        self.assertEqual(result['rooms']['kitchen']['travel_seconds'], 200)
        self.assertEqual(json.loads(json.dumps(result)), result)
        result['rooms']['kitchen']['predicted_pm25'] = 999
        self.assertEqual(sim.get_state(), before)


if __name__ == '__main__':
    unittest.main()
