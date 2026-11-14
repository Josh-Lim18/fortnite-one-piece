"""Source-policy differential and real official-state checks for Textured.

Set POKERBOTS_KIT to the extracted, unchanged organizer kit when it is elsewhere.
The brief in-process tables generate legal states, not a competitive ranking or
subprocess timing claim. No original source function is executed before audit.
"""
import ast
from collections import Counter
import importlib.util
import os
from pathlib import Path
import random
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
KIT = Path(os.environ.get("POKERBOTS_KIT", str(
    ROOT.parent / "kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit")))
sys.path.insert(0, str(KIT))
from engine import FixedHandsTable


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


port = load("textured_port", ROOT / "candidates/imported/devfun_textured.py")
source = load("textured_upstream", ROOT / "research/sources/textured_upstream.py")


def state(n=8, seat=3, button=0, **overrides):
    bets = [0] * n
    bets[(button + 1) % n] = 10
    bets[(button + 2) % n] = 20
    owed = 20 - bets[seat]
    value = {
        "seat": seat, "button": button, "stacks": [2000 - bet for bet in bets],
        "bets": bets, "folded": [False] * n, "hole_cards": ["As", "Ah"],
        "board": [], "street": "preflop", "big_blind": 20, "small_blind": 10,
        "pot": 30, "to_call": owed, "min_raise_to": 40, "max_raise_to": 2000,
        "legal_actions": (["fold", "call"] if owed else ["check"]) + ["raise"],
        "hand_number": 1,
        "history": [
            {"seat": (button + 1) % n, "street": "preflop", "action": "small_blind", "amount": 10},
            {"seat": (button + 2) % n, "street": "preflop", "action": "big_blind", "amount": 20},
        ],
    }
    value.update(overrides)
    return value


def clean_source_action(raw, value):
    """Only normalize the two API contracts, with no policy changes."""
    action = raw["action"]
    legal = value["legal_actions"]
    if action in ("bet", "raise") and "raise" in legal:
        return {"action": "raise", "amount": max(value["min_raise_to"],
                min(raw["amount"], value["max_raise_to"]))}
    if action in legal:
        return {"action": action}
    return {"action": "check" if "check" in legal else "fold"}


class TexturedPolicyTests(unittest.TestCase):
    def test_opening_ranges_sizing_and_classifiers_retained(self):
        self.assertEqual(port.OPENING_RANGES, source.OPENING_RANGES)
        self.assertEqual(port.SIZING, source.SIZING)
        rng = random.Random(720)
        deck = [rank + suit for rank in "23456789TJQKA" for suit in "shdc"]
        for _ in range(1000):
            draw = rng.sample(deck, 7)
            self.assertEqual(port._hand_class(draw[:2]), source._hand_class(draw[:2]))
            for length in (3, 4, 5):
                self.assertEqual(port._board_texture(draw[2:2 + length]),
                                 source._board_texture(draw[2:2 + length]))

    def test_all_seat_button_positions_and_extra_early_ranges(self):
        expected = {
            6: ["BTN", "SB", "BB", "UTG", "MP", "CO"],
            7: ["BTN", "SB", "BB", "UTG", "UTG", "MP", "CO"],
            8: ["BTN", "SB", "BB", "UTG", "UTG", "UTG", "MP", "CO"],
        }
        for count, positions in expected.items():
            for button in range(count):
                for seat in range(count):
                    want = positions[(seat - button) % count]
                    value = state(n=count, seat=seat, button=button)
                    self.assertEqual(port._position(seat, button, count), want)
                    mapped = port._adapt_state(value)
                    self.assertEqual(source.SEAT_TO_POS[mapped["selfSeatNumber"]], want)
                    self.assertEqual(port.Agent().act(value), {"action": "raise", "amount": 80})

    def test_blind_facing_open_recognition_preserves_real_price(self):
        value = state(hole_cards=["7s", "7h"], seat=7)  # CO opens 77; defend range excludes it
        mapped = port._adapt_state(value)
        self.assertTrue(mapped["_unraised_preflop"])
        self.assertEqual(mapped["allowedActions"]["callChips"], 20)
        self.assertEqual(source.decide(mapped)["action"], "fold")
        self.assertEqual(port.Agent().act(value), {"action": "raise", "amount": 80})
        # A prior voluntary raise prevents the source opening branch even if the
        # live bet happens to be no bigger than the blind (short-raise edge case).
        value["history"].append({"seat": 4, "street": "preflop", "action": "raise", "amount": 20})
        self.assertFalse(port._unraised_preflop(value))
        self.assertEqual(port.Agent().act(value), {"action": "fold"})
        value["history"] = []
        value["bets"][4] = 60
        self.assertFalse(port._unraised_preflop(value))

    def test_deadline_guard_removed_without_suppressing_action(self):
        mapped = port._adapt_state(state())
        self.assertEqual(source.decide(mapped, deadline_s=.010)["action"], "fold")
        self.assertEqual(port.decide(mapped, deadline_s=.010)["action"], "raise")

    def test_explicit_raise_to_not_increment_and_allin_clamping(self):
        agent = port.Agent()
        # SB already has 10 invested; output is 80 total, never 90.
        self.assertEqual(agent.act(state(seat=1)), {"action": "raise", "amount": 80})
        self.assertEqual(agent.act(state(min_raise_to=35, max_raise_to=35)),
                         {"action": "raise", "amount": 35})
        self.assertEqual(agent.act(state(min_raise_to=40, max_raise_to=70)),
                         {"action": "raise", "amount": 70})
        value = state(hole_cards=["Ah", "Kd"], board=["As", "7d", "2c"], street="flop",
                      bets=[20] * 8, pot=300, to_call=0,
                      legal_actions=["check", "raise"], min_raise_to=40, max_raise_to=1000)
        self.assertEqual(agent.act(value), {"action": "raise", "amount": 99})

    def test_forbidden_raise_is_legal_for_call_and_free_check(self):
        for legal, owed, expected in [(["fold", "call"], 20, "call"), (["check"], 0, "check")]:
            value = state(legal_actions=legal, to_call=owed, min_raise_to=None, max_raise_to=None)
            self.assertEqual(port.Agent().act(value), {"action": expected})

    def test_inherited_coarse_postflop_flaws_preserved(self):
        agent = port.Agent()
        # Pocket AA does not share a rank with this board: source checks it.
        value = state(board=["Ks", "8d", "2c"], street="flop", to_call=0,
                      legal_actions=["check", "raise"])
        self.assertEqual(agent.act(value), {"action": "check"})
        # Even a royal flush can fold: source tests only hole/board rank overlap.
        value = state(hole_cards=["As", "Ks"], board=["Qs", "Js", "Ts", "2d", "7h"],
                      street="river", to_call=20, pot=300)
        self.assertEqual(agent.act(value), {"action": "fold"})
        # A wheel-connected A23 board is still classified dry by the source.
        self.assertEqual(port._board_texture(["As", "2h", "3d"]), "dry")

    def test_source_differential_when_mapping_valid(self):
        rng = random.Random(730)
        deck = [r + s for r in "23456789TJQKA" for s in "shdc"]
        for index in range(3000):
            n = 7 + index % 2
            seat, button = rng.randrange(n), rng.randrange(n)
            draw = rng.sample(deck, 7)
            board_size = rng.choice([0, 3, 4, 5])
            owed = rng.choice([0, 20, 80, 400])
            low, high = rng.choice([(40, 2000), (400, 800), (30, 30), (None, None)])
            legal = (["fold", "call"] if owed else ["check"]) + (["raise"] if low else [])
            value = state(n=n, seat=seat, button=button, hole_cards=draw[:2],
                          board=draw[2:2 + board_size], street={0: "preflop", 3: "flop", 4: "turn", 5: "river"}[board_size],
                          to_call=owed, legal_actions=legal, min_raise_to=low, max_raise_to=high,
                          pot=rng.randrange(30, 2001),
                          history=[{"seat": (seat + 1) % n, "action": "raise", "amount": 80, "street": "preflop"}])
            mapped = port._adapt_state(value)
            self.assertFalse(mapped["_unraised_preflop"])
            expected = clean_source_action(source.decide(mapped, deadline_s=10), value)
            self.assertEqual(port.Agent().act(value), expected)

    def test_packaging_python312_grammar_stdlib_and_size(self):
        candidate = ROOT / "candidates/imported/devfun_textured.py"
        text = candidate.read_text(encoding="utf-8")
        tree = ast.parse(text, feature_version=(3, 12))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imports, {"typing"})
        self.assertFalse(any(isinstance(node, ast.Import) for node in ast.walk(tree)))
        self.assertLess(candidate.stat().st_size, 200000)
        self.assertIn("Copyright (c) 2026 dev.fun", text)
        self.assertIn("THE SOFTWARE IS PROVIDED", text)

    def test_actual_official_states_all_structures_and_short_stacks(self):
        case = self
        coverage = Counter()
        structures = ("no_limit", "pot_limit", "fixed_limit")

        class Probe:
            def __init__(self, seed, candidate_plays):
                self.rng = random.Random(seed)
                self.agent = port.Agent()
                self.candidate_plays = candidate_plays

            def start_table(self, seat, info):
                pass

            def hand_end(self, summary):
                pass

            def act(self, value):
                decision = self.agent.act(value)
                legal = value["legal_actions"]
                case.assertIn(decision["action"], legal, (decision, value))
                if decision["action"] == "raise":
                    case.assertIs(type(decision["amount"]), int)
                    case.assertLessEqual(value["min_raise_to"], decision["amount"])
                    case.assertLessEqual(decision["amount"], value["max_raise_to"])
                coverage[(len(value["stacks"]), value["betting"])] += 1
                coverage[value["street"]] += 1
                if "raise" not in legal:
                    coverage["raising_closed"] += 1
                if "raise" in legal and value["min_raise_to"] == value["max_raise_to"]:
                    coverage["single_raise_amount"] += 1
                    if value["max_raise_to"] == value["bets"][value["seat"]] + value["stacks"][value["seat"]]:
                        coverage["allin_bound"] += 1
                mapped = port._adapt_state(value)
                if not (mapped["_unraised_preflop"] and value["to_call"] > 0):
                    expected = clean_source_action(source.decide(mapped), value)
                    case.assertEqual(decision, expected)
                    coverage["source_differential"] += 1
                if self.candidate_plays:
                    return decision
                # Exploratory opponents generate unusual real bounds/states;
                # all observed states are checked before selecting this action.
                if "raise" in legal and self.rng.random() < .28:
                    choices = [value["min_raise_to"], value["max_raise_to"]]
                    return {"action": "raise", "amount": self.rng.choice(choices)}
                if "call" in legal:
                    return {"action": "call" if self.rng.random() < .85 else "fold"}
                return {"action": "check"}

        for n in (7, 8):
            for structure_index, structure in enumerate(structures):
                for stack in (35, 55, 2000):
                    roster = [Probe(9000 + seat, candidate_plays=(seat == 0)) for seat in range(n)]
                    result = FixedHandsTable(roster, hands=8, seed=800 + n + structure_index + stack,
                        config={"betting": structure, "starting_stack": stack,
                                "fixed_blinds": (10, 20), "raise_cap": 4 if structure == "fixed_limit" else None}).play()
                    self.assertEqual(sum(result["chips"]), 0)
                    self.assertEqual(result["hands"], 8)
        for n in (7, 8):
            for structure in structures:
                self.assertGreater(coverage[(n, structure)], 0)
        for key in ("preflop", "flop", "turn", "river", "raising_closed", "single_raise_amount", "allin_bound", "source_differential"):
            self.assertGreater(coverage[key], 0, key)
        print("\nOfficial-state coverage:", {str(key): count for key, count in coverage.items()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
