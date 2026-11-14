"""Focused VIVelev adapter checks; no upstream module is executed.

Run: python research/checks/test_vivelev.py
Uses the downloaded official kit only to generate legal engine states.
"""
import ast
from collections import Counter
import importlib.util
import os
from itertools import combinations
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
BOT_PATH = ROOT / "candidates/imported/vivelev_monte_carlo.py"
KIT = Path(os.environ.get("POKERBOTS_KIT", str(
    ROOT.parent / "kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit")))
spec = importlib.util.spec_from_file_location("vivelev_candidate", BOT_PATH)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def five_score(cards):
    """Slow independent five-card reference using multiplicities and sorting."""
    counts = Counter(c >> 2 for c in cards)
    ranks = sorted(counts, reverse=True)
    flush = len({c & 3 for c in cards}) == 1
    straight = -1
    if len(ranks) == 5:
        if ranks[0] - ranks[-1] == 4:
            straight = ranks[0]
        elif ranks == [12, 3, 2, 1, 0]:
            straight = 3
    groups = sorted(((count, rank) for rank, count in counts.items()), reverse=True)
    if flush and straight >= 0:
        return (8, straight)
    if groups[0][0] == 4:
        return (7, groups[0][1], groups[1][1])
    if [group[0] for group in groups] == [3, 2]:
        return (6, groups[0][1], groups[1][1])
    if flush:
        return (5, *ranks)
    if straight >= 0:
        return (4, straight)
    if groups[0][0] == 3:
        return (3, groups[0][1], *sorted((r for r, n in counts.items() if n == 1), reverse=True))
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    singles = sorted((r for r, n in counts.items() if n == 1), reverse=True)
    if len(pairs) == 2:
        return (2, *pairs, *singles)
    if pairs:
        return (1, *pairs, *singles)
    return (0, *ranks)


def pack(score):
    return (score[0] << 20) | sum(rank << (16 - 4 * i) for i, rank in enumerate(score[1:]))


def state_fixture():
    return {
        "hole_cards": ["As", "Kd"], "board": [], "street": "preflop",
        "seat": 0, "button": 7, "stacks": [1980] * 8, "bets": [20] * 8,
        "folded": [False] * 8, "pot": 160, "to_call": 20,
        "min_raise_to": 60, "max_raise_to": 2000,
        "legal_actions": ["fold", "call", "raise"], "big_blind": 20,
        "small_blind": 10, "hand_number": 1, "history": [],
    }


def assert_legal(test, action, state):
    test.assertIn(action["action"], state["legal_actions"])
    if action["action"] == "raise":
        test.assertIsInstance(action["amount"], int)
        test.assertGreaterEqual(action["amount"], state["min_raise_to"])
        test.assertLessEqual(action["amount"], state["max_raise_to"])


class EvaluatorTests(unittest.TestCase):
    def test_named_edge_hands(self):
        examples = [
            ("As Ks Qs Js Ts 2h 3d", 8),
            ("As 2s 3s 4s 5s Kd Qh", 8),
            ("As Ah Ad Ac Kd Qh 2h", 7),
            ("As Ah Ad Ks Kh Kc 2d", 6),
            ("As Ks 9s 4s 2s Qh Qd", 5),
            ("As 2h 3d 4c 5s Kd Qh", 4),
            ("As Ah Ad Ks Qd 8c 3h", 3),
            ("As Ah Ks Kh Qd Qc Js", 2),
            ("As Ah Kd Qc Js 8h 3h", 1),
            ("As Kd Qc Js 9h 5d 2s", 0),
        ]
        for hand, category in examples:
            cards = [bot._card(c) for c in hand.split()]
            expected = max(five_score(combination) for combination in combinations(cards, 5))
            with self.subTest(hand=hand):
                self.assertEqual(bot._evaluate(cards), pack(expected))
                self.assertEqual(bot._evaluate(cards) >> 20, category)

    def test_seeded_random_differential(self):
        rng = random.Random(841571)
        for size in (5, 6, 7):
            for _ in range(400):
                cards = rng.sample(range(52), size)
                expected = max(five_score(combination) for combination in combinations(cards, 5))
                self.assertEqual(bot._evaluate(cards), pack(expected), cards)

    def test_wheel_and_kicker_order(self):
        ev = lambda text: bot._evaluate([bot._card(c) for c in text.split()])
        self.assertLess(ev("As 2h 3d 4c 5s"), ev("2s 3h 4d 5c 6s"))
        self.assertGreater(ev("As Ah Ks Kh Qd Qc Js"), ev("As Ah Ks Kh Jd Jc Ts"))
        self.assertEqual(ev("As Ks Qs Js Ts 2h 3d"), ev("As Ks Qs Js Ts 4h 5d"))


class MonteCarloTests(unittest.TestCase):
    def test_independent_seeded_rollouts(self):
        hole = list(map(bot._card, ["As", "Ah"]))
        board = list(map(bot._card, ["2c", "7d", "Jh"]))
        first = bot._estimate_win_rate(hole, board, 7, random.Random(91), max_samples=32)
        second = bot._estimate_win_rate(hole, board, 7, random.Random(91), max_samples=32)
        self.assertEqual(first, second)
        self.assertEqual(first[1], 32)
        self.assertGreaterEqual(first[0], 0)
        self.assertLessEqual(first[0], 1)

    def test_ties_are_full_wins_as_upstream(self):
        board = list(map(bot._card, ["As", "Ks", "Qs", "Js", "Ts"]))
        hole = list(map(bot._card, ["2c", "3d"]))
        self.assertEqual(bot._estimate_win_rate(hole, board, 7, random.Random(3)), (1.0, 32))

    def test_rollouts_have_no_duplicate_or_known_cards(self):
        hole = list(map(bot._card, ["As", "Kd"]))
        board = list(map(bot._card, ["2c", "7d", "Jh"]))
        known = set(hole + board)
        test = self
        class CheckedRandom(random.Random):
            def sample(self, population, k):
                test.assertFalse(known.intersection(population))
                result = super().sample(population, k)
                test.assertEqual(len(result), len(set(result)))
                test.assertEqual(k, 2 + 7 * 2)
                return result
        bot._estimate_win_rate(hole, board, 7, CheckedRandom(9), max_samples=5)

    def test_deadline_finishes_at_least_one_and_stops(self):
        rate, samples = bot._estimate_win_rate(
            list(map(bot._card, ["As", "Kd"])), [], 7, random.Random(9), deadline=0.0)
        self.assertIn(rate, (0.0, 1.0))
        self.assertEqual(samples, 1)


class PolicyTests(unittest.TestCase):
    def test_original_strict_thresholds(self):
        state = state_fixture()
        expected = [
            (0.0, {"action": "fold"}), (0.5, {"action": "fold"}),
            (0.50001, {"action": "call"}), (0.75, {"action": "call"}),
            (0.75001, {"action": "raise", "amount": 60}),
            (0.85, {"action": "raise", "amount": 60}),
            (0.85001, {"action": "raise", "amount": 2000}),
        ]
        for rate, action in expected:
            self.assertEqual(bot._policy(rate, state), action)

    def test_unavailable_raise_and_free_check(self):
        state = state_fixture()
        state.update(legal_actions=["fold", "call"], min_raise_to=None, max_raise_to=None)
        self.assertEqual(bot._policy(0.99, state), {"action": "call"})
        state.update(legal_actions=["check"], to_call=0)
        for rate in (0, 0.5, 0.7, 0.8, 0.99):
            self.assertEqual(bot._policy(rate, state), {"action": "check"})

    def test_all_in_opponent_is_not_folded(self):
        state = state_fixture()
        state["folded"] = [False, False, True, True, True, True, True, True]
        state["stacks"][1] = 0
        self.assertEqual(bot._remaining_opponents(state), 1)
        state["folded"][1] = True
        self.assertEqual(bot._remaining_opponents(state), 0)

    def test_short_all_in_raise_and_limits(self):
        state = state_fixture()
        for low, high in ((60, 2000), (45, 45), (60, 140), (40, 40)):
            state.update(min_raise_to=low, max_raise_to=high)
            for rate in (0, 0.6, 0.8, 0.95):
                assert_legal(self, bot._policy(rate, state), state)

    def test_official_engine_generated_states(self):
        self.assertTrue(KIT.is_dir(), "Official kit required for this integration check")
        sys.path.insert(0, str(KIT))
        from engine import FixedHandsTable
        seen = {"count": 0, "streets": set()}
        test = self

        class ProbePlayer:
            def __init__(self, seed):
                self.agent = bot.Agent()
                self.random = random.Random(seed)
            def start_table(self, seat, info):
                self.agent.on_table_start(info)
            def act(self, state):
                # Probe the candidate on real states; varied independent choices
                # drive the engine into calls, raises, folds and later streets.
                decision = self.agent.act(state)
                assert_legal(test, decision, state)
                test.assertLessEqual(self.agent.last_samples, bot.MAX_SAMPLES)
                seen["count"] += 1
                seen["streets"].add(state["street"])
                action = self.random.choice(state["legal_actions"])
                if action == "raise":
                    return {"action": action, "amount": state["min_raise_to"]}
                return {"action": action}
            def hand_end(self, summary):
                pass

        for seats in (7, 8):
            for structure in ("no_limit", "pot_limit", "fixed_limit"):
                players = [ProbePlayer(300 + i) for i in range(seats)]
                FixedHandsTable(players, hands=4, seed=915,
                                config={"betting": structure, "raise_cap": 3}).play()
        self.assertGreater(seen["count"], 100)
        self.assertEqual(seen["streets"], {"preflop", "flop", "turn", "river"})


class PackagingTests(unittest.TestCase):
    def test_single_file_stdlib_and_python312_syntax(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, feature_version=(3, 12))
        imports = {alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"random", "time"})
        self.assertFalse(any(isinstance(node, ast.ImportFrom) for node in ast.walk(tree)))
        self.assertLessEqual(BOT_PATH.stat().st_size, 200_000)
        self.assertIn("Copyright (c) 2018 Victor Velev", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
