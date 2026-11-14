"""NUCATS source-port fidelity and official-state boundary checks.

Run: python research/checks/test_nucats.py
Optional: POKERBOTS_KIT points to the official kit directory.
Only inspected upstream card helpers and the extracted decide() are executed;
the upstream socket client/runner is never imported. No full games are played.
"""
import ast
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import random
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
BOT_PATH = ROOT / "candidates/imported/nucats_starter.py"
SOURCES = ROOT / "research/sources"
KIT = Path(os.environ.get("POKERBOTS_KIT", str(
    ROOT.parent / "kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit")))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bot = load("nucats_port", BOT_PATH)
source_cards = load("nucats_cards", SOURCES / "nucats_cards_upstream.py")
source_tree = ast.parse((SOURCES / "nucats_bot_upstream.py").read_text(encoding="utf-8"))
source_decide = next(node for node in source_tree.body
                     if isinstance(node, ast.FunctionDef) and node.name == "decide")
source_namespace = {
    "hand_strength": source_cards.hand_strength,
    "is_pair": source_cards.is_pair,
    "rank": source_cards.rank,
    "raise_to": lambda amount: {"action": "raise", "amount": amount},
    "call": lambda: {"action": "call"},
    "check": lambda: {"action": "check"},
    "fold": lambda: {"action": "fold"},
}
exec(compile(ast.Module(body=[source_decide], type_ignores=[]),
             "<inspected upstream decide>", "exec"), source_namespace)


def upstream_action(state):
    owed = state["to_call"]
    proxy = SimpleNamespace(
        my_cards=state["hole_cards"], board=state["board"],
        street=state["street"], can_raise="raise" in state["legal_actions"],
        can_check="check" in state["legal_actions"],
        min_raise=state["min_raise_to"], max_raise=state["max_raise_to"],
        pot_odds=owed / (state["pot"] + owed) if owed else 0.0)
    return source_namespace["decide"](proxy)


def fixture(cards=("As", "Ah"), board=(), street="preflop",
            owed=20, pot=30, low=40, high=2000, n=8):
    legal = ["fold", "call"] if owed else ["check"]
    if low is not None:
        legal.append("raise")
    return {
        "hole_cards": list(cards), "board": list(board), "street": street,
        "seat": 0, "button": n - 1, "stacks": [2000] * n,
        "bets": [0] * n, "folded": [False] * n,
        "pot": pot, "to_call": owed, "min_raise_to": low,
        "max_raise_to": high, "legal_actions": legal,
        "small_blind": 10, "big_blind": 20, "hand_number": 1,
        "history": [], "betting": "no_limit", "raise_cap": None,
    }


def assert_legal(testcase, action, state):
    testcase.assertIn(action["action"], state["legal_actions"], state)
    if action["action"] == "raise":
        testcase.assertIs(type(action["amount"]), int)
        testcase.assertGreaterEqual(action["amount"], state["min_raise_to"])
        testcase.assertLessEqual(action["amount"], state["max_raise_to"])


class SourceFidelityTests(unittest.TestCase):
    def test_preserved_upstream_blob_hashes(self):
        expected = {
            "nucats_bot_upstream.py": "e7c26b10cd83017cdceaf5848b8de78f18031cec",
            "nucats_cards_upstream.py": "dd509f079524d5b72edc7f7001c24646c2d4a253",
            "nucats_LICENSE.txt": "a21fef204cd99bb4031be9076ac095a330a31c4e",
        }
        for filename, digest in expected.items():
            data = (SOURCES / filename).read_bytes()
            header = ("blob " + str(len(data)) + "\0").encode()
            self.assertEqual(hashlib.sha1(header + data).hexdigest(), digest, filename)

    def test_seeded_differential_against_original_decide(self):
        rng = random.Random(6726)
        deck = [rank + suit for rank in "23456789TJQKA" for suit in "cdhs"]
        agent = bot.Agent()
        for _ in range(1200):
            street, count = rng.choice([("preflop", 0), ("flop", 3),
                                        ("turn", 4), ("river", 5)])
            cards = rng.sample(deck, 2 + count)
            low = rng.choice([None, 40, 60, 80])
            high = None if low is None else rng.choice([low, low + 5, 2000])
            st = fixture(cards[:2], cards[2:], street, rng.choice([0, 15, 20, 150]),
                         rng.randint(30, 3000), low, high, rng.choice([7, 8]))
            before = copy.deepcopy(st)
            result = agent.act(st)
            self.assertEqual(result, upstream_action(st), st)
            assert_legal(self, result, st)
            self.assertEqual(st, before, "Agent must not mutate public state")

    def test_source_strength_quirks_and_thresholds_are_preserved(self):
        # Board-made two pair alone reaches 0.7 and raises, as upstream.
        st = fixture(("3c", "4d"), ("As", "Ah", "Ks", "Kh", "2d"), "river")
        self.assertEqual(bot.hand_strength(st["hole_cards"], st["board"]), 0.7)
        self.assertEqual(bot.Agent().act(st), {"action": "raise", "amount": 120})
        # A board-only pair also remains an automatic strength-based call.
        st = fixture(("2c", "7d"), ("As", "Ah", "Kd"), "flop",
                     owed=1000, pot=1100, low=None, high=None)
        self.assertEqual(bot.Agent().act(st), {"action": "call"})
        self.assertEqual(bot.Agent().act(fixture(("9c", "9d"))),
                         {"action": "raise", "amount": 120})
        self.assertEqual(bot.Agent().act(fixture(("8c", "8d"))), {"action": "call"})

    def test_pot_odds_boundary(self):
        agent = bot.Agent()
        self.assertEqual(agent.act(fixture(("2c", "7d"), owed=20, pot=80)),
                         {"action": "call"})
        self.assertEqual(agent.act(fixture(("2c", "7d"), owed=20, pot=79)),
                         {"action": "fold"})

    def test_legal_short_and_fixed_raise_totals(self):
        agent = bot.Agent()
        for low, high, expected in [(40, 2000, 120), (40, 65, 65),
                                    (25, 25, 25), (60, 60, 60)]:
            st = fixture(low=low, high=high)
            st["bets"][0] = 20  # Target is total; never add this again.
            self.assertEqual(agent.act(st), {"action": "raise", "amount": expected})

    def test_closed_raising_and_free_checks(self):
        agent = bot.Agent()
        self.assertEqual(agent.act(fixture(low=None, high=None)), {"action": "call"})
        for cards in (("As", "Ah"), ("2c", "7d")):
            self.assertEqual(agent.act(fixture(cards, owed=0, low=None, high=None)),
                             {"action": "check"})
        self.assertEqual(agent.act(fixture(("2c", "7d"), low=None, high=None)),
                         {"action": "fold"})

    def test_all_in_opponents_button_and_chip_scale(self):
        agent = bot.Agent()
        st = fixture(("2c", "7d"), owed=15, pot=60, low=None, high=None)
        st["stacks"][0] = 15
        st["stacks"][1] = 0
        st["folded"][1] = False  # All-in opponent stays in hand.
        expected = agent.act(st)
        self.assertEqual(expected, {"action": "call"})
        for n in (7, 8):
            for button in range(n):
                other = copy.deepcopy(st)
                other["button"] = button
                other["stacks"] = other["stacks"][:n]
                other["bets"] = other["bets"][:n]
                other["folded"] = other["folded"][:n]
                self.assertEqual(agent.act(other), expected)
        # Policy is ratio/hand based: no hidden 1,000-chip source constant.
        scaled = fixture(("2c", "7d"), owed=150, pot=600, low=None, high=None)
        self.assertEqual(agent.act(scaled), expected)


class OfficialStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not KIT.is_dir():
            raise AssertionError("Official kit missing; set POKERBOTS_KIT")
        sys.path.insert(0, str(KIT))
        from engine import FixedHandsTable
        cls.Table = FixedHandsTable

    def betting_phase(self, n, structure, street, mode="ordinary"):
        """Exercise the official state's actual producer without a full game."""
        test = self
        observed = []
        agent = bot.Agent()

        class Probe:
            def act(self, state):
                decision = agent.act(state)
                test.assertEqual(decision, upstream_action(state))
                assert_legal(test, decision, state)
                observed.append(copy.deepcopy(state))
                if mode == "short_reopen":
                    if state["seat"] == 1 and "raise" in state["legal_actions"]:
                        return {"action": "raise", "amount": state["max_raise_to"]}
                elif mode == "ordinary" and "raise" in state["legal_actions"]:
                    return {"action": "raise", "amount": state["min_raise_to"]}
                return {"action": "check" if "check" in state["legal_actions"] else "call"}

        table = self.Table([Probe() for _ in range(n)], hands=1, seed=61,
                           config={"betting": structure, "raise_cap": 3})
        deck = random.Random(610 + n).sample(range(52), 52)
        hole = [deck[2*i:2*i+2] for i in range(n)]
        board_count = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]
        board = deck[2*n:2*n+board_count]
        bets = ([0] * (n-2) + [10, 20]) if street == "preflop" else [0] * n
        contrib = list(bets) if street == "preflop" else [40] * n
        folded = [False] * n
        table.stacks = [2000 - c for c in contrib]

        if mode == "short_reopen":
            bets = [0] * n
            bets[-1] = 20
            contrib = list(bets)
            table.stacks = [2000 - c for c in contrib]
            table.stacks[1] = 25
        elif mode in ("short_call", "free_check"):
            folded = [False, False] + [True] * (n-2)
            bets = [0] * n
            bets[1] = 20 if mode == "short_call" else 0
            contrib = [20] * n
            table.stacks = [15 if mode == "short_call" else 1980, 0] + [1980] * (n-2)

        def put(seat, amount):
            amount = min(amount, table.stacks[seat])
            table.stacks[seat] -= amount
            bets[seat] += amount
            contrib[seat] += amount

        table._betting_round(street, 0, hole, board, bets, contrib, folded,
                             [], {"events": []}, 1, n-1, 10, 20, 0, put)
        return observed

    def test_all_structures_and_streets_from_official_engine(self):
        count = 0
        seen = set()
        closed = False
        for n in (7, 8):
            for structure in ("no_limit", "pot_limit", "fixed_limit"):
                for street in ("preflop", "flop", "turn", "river"):
                    states = self.betting_phase(n, structure, street)
                    count += len(states)
                    seen.update(st["street"] for st in states)
                    closed |= any("raise" not in st["legal_actions"] for st in states)
                    self.assertTrue(states)
                    self.assertTrue(all(st["betting"] == structure for st in states))
        self.assertGreater(count, 100)
        self.assertEqual(len(seen), 4)
        self.assertTrue(closed)

    def test_official_short_all_in_and_raising_not_reopened(self):
        for n in (7, 8):
            for structure in ("no_limit", "pot_limit", "fixed_limit"):
                states = self.betting_phase(n, structure, "preflop", "short_reopen")
                first_short = next(st for st in states if st["seat"] == 1)
                self.assertEqual((first_short["min_raise_to"], first_short["max_raise_to"]), (25, 25))
                reopened = [st for st in states if st["seat"] == 0][-1]
                self.assertEqual(reopened["to_call"], 5)
                self.assertNotIn("raise", reopened["legal_actions"])
                self.assertIsNone(reopened["min_raise_to"])
                self.assertEqual(reopened["stacks"][1], 0)
                self.assertFalse(reopened["folded"][1])

    def test_official_stack_capped_call_and_check_against_all_in(self):
        for n in (7, 8):
            for structure in ("no_limit", "pot_limit", "fixed_limit"):
                short = self.betting_phase(n, structure, "preflop", "short_call")[0]
                self.assertEqual(short["to_call"], 15)
                self.assertEqual(short["legal_actions"], ["fold", "call"])
                free = self.betting_phase(n, structure, "flop", "free_check")[0]
                self.assertEqual(free["legal_actions"], ["check"])
                self.assertEqual(bot.Agent().act(free), {"action": "check"})


class PackagingTests(unittest.TestCase):
    def test_single_file_stdlib_syntax_and_license(self):
        text = BOT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(text, feature_version=(3, 12))
        modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(modules, {"collections"})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
        self.assertLess(BOT_PATH.stat().st_size, 200_000)
        self.assertIn((SOURCES / "nucats_LICENSE.txt").read_text(encoding="utf-8").strip(), text)
        self.assertTrue(callable(bot.Agent().act))


if __name__ == "__main__":
    unittest.main(verbosity=2)
