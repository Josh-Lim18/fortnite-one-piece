"""Benchmark opponents in candidates/imported/: packaging, legal play, cost.

Run: KIT=<starter kit> python3 candidates/imported/tests/test_opponents.py
The official engine (`kit/` on branch poker/live) deals real states; every
action each opponent returns must already be legal, never fixed up by the
engine. Prints laptop ms per act for each opponent.
"""
import ast
import importlib.util
import os
from pathlib import Path
import random
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
IMPORTED = HERE.parent
REPO = HERE.parents[2]
KIT = Path(os.environ.get("KIT", REPO / "kit"))
if not (KIT / "engine" / "game.py").is_file():
    raise SystemExit("official kit not found; set KIT=path to the starter kit")
sys.path.insert(0, str(KIT))
from engine import FixedHandsTable  # noqa: E402

OPPONENTS = ("devfun_textured", "fullhouse_floorfix", "nucats_starter")


def load(name):
    spec = importlib.util.spec_from_file_location(name, IMPORTED / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def illegal(state, move):
    """Why `move` is not a legal kit action in `state`, or None."""
    if not isinstance(move, dict):
        return "not a dict"
    act, legal = move.get("action"), state["legal_actions"]
    if act not in legal:
        return "%r not in %r" % (act, legal)
    if act == "raise":
        amount = move.get("amount")
        if type(amount) is not int:
            return "raise amount %r is not an int" % (amount,)
        if not state["min_raise_to"] <= amount <= state["max_raise_to"]:
            return "raise to %d outside [%d, %d]" % (
                amount, state["min_raise_to"], state["max_raise_to"])
    return None


class Audited:
    def __init__(self, module, test, times):
        self.module, self.test, self.times = module, test, times

    def start_table(self, seat, info):
        self.agent = self.module.Agent()
        if hasattr(self.agent, "on_table_start"):
            self.agent.on_table_start(info)

    def act(self, state):
        t = time.perf_counter()
        move = self.agent.act(state)
        self.times.append(time.perf_counter() - t)
        self.test.assertIsNone(illegal(state, move), (self.module.__name__, state, move))
        return move

    def hand_end(self, summary):
        if hasattr(self.agent, "on_hand_end"):
            self.agent.on_hand_end(summary)


class Opponents(unittest.TestCase):
    def test_packaging(self):
        for name in OPPONENTS:
            path = IMPORTED / (name + ".py")
            tree = ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 12))
            names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                     for a in n.names}
            names |= {n.module.split(".")[0] for n in ast.walk(tree)
                      if isinstance(n, ast.ImportFrom) and n.module}
            with self.subTest(name):
                self.assertTrue(names <= set(sys.stdlib_module_names), names)
                self.assertTrue(any(isinstance(n, ast.ClassDef) and n.name == "Agent"
                                    for n in tree.body))
                self.assertLess(path.stat().st_size, 200_000)
                self.assertIn("MIT License", path.read_text(encoding="utf-8"))
                self.assertTrue((IMPORTED / "LICENSES" / (name + ".txt")).is_file())

    def test_legal_play_on_engine_states(self):
        rng = random.Random(1114)
        for name in OPPONENTS:
            module, times = load(name), []
            for seats in (7, 8):
                for betting in ("no_limit", "pot_limit", "fixed_limit"):
                    roster = [Audited(module, self, times) for _ in range(seats)]
                    FixedHandsTable(roster, hands=40, seed=rng.randrange(10 ** 6),
                                    config={"betting": betting, "raise_cap": 3}).play()
            times.sort()
            print("%-22s %5d acts, mean %.3f ms, p99 %.3f ms, max %.3f ms" % (
                name, len(times), 1000 * sum(times) / len(times),
                1000 * times[int(.99 * len(times))], 1000 * times[-1]))

    def test_same_seed_same_result(self):
        # Paired benchmarks need opponents that don't depend on wall-clock time.
        def chips(seed):
            roster = [Audited(load(OPPONENTS[i % len(OPPONENTS)]), self, []) for i in range(8)]
            return FixedHandsTable(roster, hands=150, seed=seed).play()["chips"]
        self.assertEqual(chips(7), chips(7))


if __name__ == "__main__":
    unittest.main(verbosity=2)
