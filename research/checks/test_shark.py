"""Differential policy and Imperial action-boundary checks for the Shark port."""
import importlib.util
from pathlib import Path
import random
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


port = load("shark_port", ROOT / "candidates/imported/fullhouse_shark.py")
source = load("shark_source", ROOT / "research/sources/fullhouse_shark.py")


class SharkTests(unittest.TestCase):
    def state(self, cards=("As", "Ah"), n=8, seat=0, street="preflop", owed=20,
              pot=30, low=40, high=2000):
        return dict(hole_cards=list(cards), stacks=[2000] * n, bets=[0] * n,
                    seat=seat, street=street, to_call=owed, pot=pot,
                    min_raise_to=low, max_raise_to=high,
                    legal_actions=["fold", "call" if owed else "check"] +
                    (["raise"] if low is not None else []))

    def test_raise_bounds_and_closed_raising(self):
        agent = port.Agent()
        self.assertEqual(agent.act(self.state(low=40, high=65)),
                         {"action": "raise", "amount": 65})
        self.assertEqual(agent.act(self.state(low=40, high=40)),
                         {"action": "raise", "amount": 40})
        self.assertEqual(agent.act(self.state(low=None, high=None)), {"action": "call"})
        self.assertEqual(agent.act(self.state(low=None, high=None, owed=0)),
                         {"action": "check"})

    def test_original_rank_bug_is_explicitly_preserved(self):
        self.assertEqual(port.hand_strength(["As", "Kh"]), "medium")
        self.assertEqual(port.hand_strength(["As", "Ah"]), "strong")
        self.assertEqual(port.hand_strength(["2s", "7h"]), "weak")

    def test_matches_upstream_after_documented_action_normalisation(self):
        rng = random.Random(250)
        deck = [r + s for r in "23456789TJQKA" for s in "cdhs"]
        for i in range(1000):
            n = rng.choice([7, 8])
            st = self.state(rng.sample(deck, 2), n, rng.randrange(n),
                            rng.choice(["preflop", "flop", "turn", "river"]),
                            rng.choice([0, 20, 100, 350]), rng.randrange(30, 3000),
                            400, rng.randrange(400, 2001))
            agent = port.Agent()
            agent.rng.seed(i)
            source.random = random.Random(i)
            raw = source.decide(dict(
                street=st["street"], amount_owed=st["to_call"], pot=st["pot"],
                your_stack=st["stacks"][st["seat"]], seat_to_act=st["seat"],
                players=st["stacks"], your_cards=st["hole_cards"],
                min_raise_to=st["min_raise_to"], your_bet_this_street=0,
                can_check="check" in st["legal_actions"]))
            if raw["action"] == "raise":
                raw["amount"] = max(st["min_raise_to"], min(raw["amount"], st["max_raise_to"]))
            elif raw["action"] == "call" and st["to_call"] == 0:
                raw = {"action": "check"}
            self.assertEqual(agent.act(st), raw, st)
            self.assertIn(raw["action"], st["legal_actions"])


if __name__ == "__main__":
    unittest.main()
