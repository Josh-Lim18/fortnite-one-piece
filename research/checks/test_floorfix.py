"""Interface/evaluator regression checks; the official kit is an oracle only.

python research/checks/test_floorfix.py --kit PATH
No full-table performance estimate or tournament ranking is produced here.
"""
from pathlib import Path
import argparse
import importlib.util
import os
import random
import statistics
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KIT = Path(os.environ.get("POKERBOTS_KIT", str(
    ROOT.parent / "kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit")))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bot = load("floorfix_candidate", ROOT / "candidates/imported/fullhouse_floorfix.py")
parser = argparse.ArgumentParser()
parser.add_argument("--kit", type=Path, default=DEFAULT_KIT)
args, unittest_args = parser.parse_known_args()
oracle = load("official_cards_oracle", args.kit / "engine/cards.py")


def cards(text):
    return [bot._Card(value) for value in text.split()]


def state(**overrides):
    value = {
        "hand_number": 1, "seat": 3, "button": 0, "hole_cards": ["As", "Ah"],
        "board": [], "street": "preflop", "stacks": [2000, 1990, 1980, 2000, 2000, 2000, 2000, 2000],
        "bets": [0, 10, 20, 0, 0, 0, 0, 0], "folded": [False] * 8,
        "pot": 30, "to_call": 20, "big_blind": 20, "small_blind": 10,
        "min_raise_to": 40, "max_raise_to": 2000,
        "legal_actions": ["fold", "call", "raise"],
        "history": [{"seat": 1, "street": "preflop", "action": "small_blind", "amount": 10},
                    {"seat": 2, "street": "preflop", "action": "big_blind", "amount": 20}],
    }
    value.update(overrides)
    return value


class EvaluatorTests(unittest.TestCase):
    def test_known_categories_and_compatibility_names(self):
        examples = [
            ("As Kd 9c 6h 3s", "High Card"), ("As Ah 9c 6h 3s", "Pair"),
            ("As Ah 9c 9h 3s", "Two Pair"), ("As Ah Ac 6h 3s", "Trips"),
            ("As 2h 3c 4d 5s", "Straight"), ("As Js 9s 6s 3s", "Flush"),
            ("As Ah Ac 6h 6s", "Full House"), ("As Ah Ac Ad 3s", "Quads"),
            ("As Ks Qs Js Ts", "Straight Flush"),
        ]
        scores = []
        for index, (hand, name) in enumerate(examples):
            score = bot._evaluate(cards(hand))
            self.assertEqual(score >> 20, index, hand)
            self.assertEqual(bot.eval7.handtype(score), name)
            scores.append(score)
        self.assertEqual(scores, sorted(scores))

    def test_wheel_double_trips_and_board_ties(self):
        wheel = bot._evaluate(cards("As 2h 3c 4d 5s"))
        self.assertLess(wheel, bot._evaluate(cards("2s 3h 4c 5d 6s")))
        self.assertEqual(wheel, bot._evaluate(cards("Ac 2s 3h 4c 5h")))
        self.assertGreater(bot._evaluate(cards("As Ah Ac Ks Kh Kc 2s")),
                           bot._evaluate(cards("Ks Kh Kc Qs Qh Qc As")))
        board = cards("As Ks Qs Js Ts")
        self.assertEqual(bot._evaluate(board), bot._evaluate(cards("2h 3c") + board))
        self.assertEqual(bot.hand_features(cards("2h 3c"), board)["commit"], 0)

    def test_twelve_thousand_random_oracle_scores_and_order(self):
        rng = random.Random(917)
        deck = [rank + suit for rank in bot.RANKS for suit in bot.SUITS]
        previous = None
        for i in range(12000):
            hand = rng.sample(deck, 5 + i % 3)
            official = oracle.evaluate([oracle.to_int(card) for card in hand])
            expected = official[0] << 20
            for offset, rank in enumerate(official[1:]):
                expected |= rank << (16 - 4 * offset)
            actual = bot._evaluate([bot._Card(card) for card in hand])
            self.assertEqual(actual, expected, hand)
            if previous:
                prev_actual, prev_official = previous
                self.assertEqual((actual > prev_actual) - (actual < prev_actual),
                                 (official > prev_official) - (official < prev_official))
            previous = actual, official


class AdapterTests(unittest.TestCase):
    def test_table_pair_bugfix_and_aa_opens_weak_hand_folds(self):
        self.assertEqual(len(bot.PREFLOP_EQ), 169)
        self.assertTrue(all(rank * 2 in bot.PREFLOP_EQ for rank in bot.RANKS))
        self.assertGreater(bot.PREFLOP_EQ["AA"], .8)
        self.assertLess(bot.PREFLOP_EQ["72o"], .4)
        self.assertEqual(bot.Agent().act(state()), {"action": "raise", "amount": 60})
        self.assertEqual(bot.Agent().act(state(hole_cards=["7s", "2h"])), {"action": "fold"})

    def test_source_conservatism_is_retained(self):
        shove = state(hole_cards=["As", "Kh"], to_call=900, pot=930, min_raise_to=1800,
                      history=[{"seat": 2, "action": "raise", "amount": 900, "street": "preflop"}])
        self.assertEqual(bot.Agent().act(shove), {"action": "fold"})
        shove["hole_cards"] = ["As", "Ah"]
        self.assertEqual(bot.Agent().act(shove)["action"], "raise")

    def test_raise_bounds_short_allin_and_forbidden_raise(self):
        agent = bot.Agent()
        # Short all-in max may be below the normal full-raise size. Official
        # min_raise_to equals max_raise_to in that state.
        for low, high, desired in [(25, 25, 60), (40, 2000, 5000), (80, 90, 3), (20, 20, 0)]:
            converted = agent._adapt_state(state(min_raise_to=low, max_raise_to=high))
            action = bot._make_raise(desired, converted)
            self.assertEqual(action["action"], "raise")
            self.assertLessEqual(low, action["amount"])
            self.assertLessEqual(action["amount"], high)
        for legal, expected in [(["fold", "call"], "call"), (["check"], "check")]:
            value = state(min_raise_to=None, max_raise_to=None, legal_actions=legal)
            self.assertEqual(agent.act(value), {"action": expected})

    def test_random_raise_bounds(self):
        rng = random.Random(18)
        agent = bot.Agent()
        for _ in range(2000):
            high = rng.randrange(1, 4000)
            low = rng.randrange(1, high + 1)
            adapted = agent._adapt_state(state(min_raise_to=low, max_raise_to=high))
            action = bot._make_raise(rng.randrange(-100, 8000), adapted)
            self.assertTrue(low <= action["amount"] <= high)

    def test_positions_use_button_and_allin_players_are_opponents(self):
        agent = bot.Agent()
        for seat in range(8):
            for button in range(8):
                adapted = agent._adapt_state(state(seat=seat, button=button))
                self.assertEqual(bot.positions(adapted),
                                 (8, button, (button + 1) % 8, (button + 2) % 8, (button - seat) % 8))
        value = state(board=["2s", "3h", "4d"], street="flop", to_call=0, pot=100,
                      legal_actions=["check", "raise"], stacks=[0, 0, 0, 2000, 0, 0, 0, 0],
                      folded=[False, False, True, False, True, True, True, True])
        with patch.object(bot, "mc_equity", return_value=.3) as equity:
            agent.act(value)
        self.assertEqual(equity.call_args.args[2], 2)

    def test_profiles_deduplicate_summaries_and_do_not_mutate_during_act(self):
        agent = bot.Agent()
        history = [{"seat": 0, "action": "raise", "street": "preflop", "amount": 60},
                   {"seat": 1, "action": "fold", "street": "preflop", "amount": 0}]
        summary = {"hand_number": 1, "history": history}
        current = agent._adapt_state(state(history=history))
        self.assertEqual(current["_profiles"]["seat_0"]["n"], 1)
        self.assertEqual(agent._counts, {})
        agent.on_hand_end(summary)
        agent.on_hand_end(summary)
        self.assertEqual(agent._counts["seat_0"]["n"], 1)
        # Even a duplicated completed-hand observation does not count twice.
        self.assertEqual(agent._adapt_state(state(history=history))["_profiles"]["seat_0"]["n"], 1)
        next_hand = agent._adapt_state(state(hand_number=2, history=history))
        self.assertEqual(next_hand["_profiles"]["seat_0"]["n"], 2)
        self.assertEqual(agent._counts["seat_0"]["n"], 1)
        agent.on_hand_end({"hand_number": 2, "history": history})
        agent.on_hand_end(summary)  # stale summaries ignored
        self.assertEqual(agent._counts["seat_0"]["n"], 2)
        self.assertEqual(bot.last_aggressor_id(current), "seat_0")
        agent.on_table_start({"seat": 3})
        self.assertEqual(agent._counts, {})
        self.assertEqual(agent._last_completed_hand, 0)

    def test_per_agent_rng_and_deadline_every_sample(self):
        first, second = bot.Agent(), bot.Agent()
        first._rng.random()
        self.assertEqual(second._rng.random(), random.Random(0xC0FFEE).random())
        rng = random.Random(1)
        saved = rng.getstate()
        with patch.object(bot, "perf_counter", return_value=1.0):
            self.assertEqual(bot.mc_equity(cards("As Ah"), cards("2s 3h 4d"), 7, 24, .9, rng), .5)
        self.assertEqual(rng.getstate(), saved)
        # First sample starts before deadline; second starts after it. The source
        # checked every 32 samples, which would fail this exact two-clock test.
        with patch.object(bot, "perf_counter", side_effect=[0.0, 1.0]) as clock:
            bot.mc_equity(cards("As Ah"), cards("2s 3h 4d"), 7, 24, .9, rng)
        self.assertEqual(clock.call_count, 2)

    def test_standalone_size_imports_and_local_timing(self):
        candidate = ROOT / "candidates/imported/fullhouse_floorfix.py"
        self.assertLess(candidate.stat().st_size, 200_000)
        import ast
        parsed = ast.parse(candidate.read_text(encoding="utf-8"))
        imports = {node.module if isinstance(node, ast.ImportFrom) else node.names[0].name
                   for node in ast.walk(parsed) if isinstance(node, (ast.Import, ast.ImportFrom))}
        self.assertEqual(imports, {"random", "time"})
        agent = bot.Agent()
        value = state(board=["2s", "3h", "4d"], street="flop", pot=200)
        durations = []
        for _ in range(200):
            start = time.perf_counter()
            action = agent.act(value)
            durations.append((time.perf_counter() - start) * 1000)
            self.assertIn(action["action"], value["legal_actions"])
        durations.sort()
        print("\nIn-process 8-seat flop timing, 200 actions (ms): "
              f"median={statistics.median(durations):.3f} p95={durations[189]:.3f} "
              f"p99={durations[197]:.3f} max={durations[-1]:.3f}; excludes IPC, not a submission guarantee")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]] + unittest_args, verbosity=2)
