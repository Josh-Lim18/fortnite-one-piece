"""Tests for analyze_preflop / hand_category / position_info in bot.py.

Run: KIT=<starter kit> python candidates/improved/tests/test_preflop.py
Scenario states come from the official engine with scripted players.
Scripts are keyed by seat offset from the button (1 = SB, 2 = BB, 3 = first
to act, 0 = button), independent of the bot's own position labels.
"""
import copy
import importlib.util
import os
from pathlib import Path
import random
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
KIT = Path(os.environ.get("KIT", REPO / "kit"))
spec = importlib.util.spec_from_file_location("lane_c_bot", HERE.parent / "bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

if not (KIT / "engine" / "game.py").is_file():
    raise SystemExit("official kit not found; set KIT=path to the starter kit")
sys.path.insert(0, str(KIT))
from engine import FixedHandsTable  # noqa: E402
from engine.game import SitAndGo  # noqa: E402

LABELS = {
    8: {3: "UTG", 4: "UTG+1", 5: "LJ", 6: "HJ", 7: "CO", 0: "BTN", 1: "SB", 2: "BB"},
    7: {3: "UTG", 4: "LJ", 5: "HJ", 6: "CO", 0: "BTN", 1: "SB", 2: "BB"},
}


class Script:
    """Scripted seats. script[offset] = list of actions, each 'fold',
    'call', 'check', 'all_in' or an int (raise to). 'capture' records the
    state and then takes the next action in the list."""

    def __init__(self, n, script):
        self.n, self.script, self.captured = n, {k: list(v) for k, v in script.items()}, []

    def player(self):
        outer = self

        class P:
            def start_table(self, seat, info):
                pass

            def act(self, state):
                off = (state["seat"] - state["button"]) % outer.n
                todo = outer.script.get(off, [])
                while todo and todo[0] == "capture":
                    todo.pop(0)
                    outer.captured.append(copy.deepcopy(state))
                step = todo.pop(0) if todo else None
                legal = state["legal_actions"]
                if isinstance(step, int):
                    return {"action": "raise", "amount": step}
                if step in ("call", "all_in"):
                    return {"action": step}
                return {"action": "check" if "check" in legal else "fold"}

            def hand_end(self, summary):
                pass
        return P()


def run_fixed(n, script, seed=3):
    s = Script(n, script)
    FixedHandsTable([s.player() for _ in range(n)], hands=1, seed=seed).play()
    return s.captured


def run_stacks(n, script, stack_by_offset, seed=4):
    """One hand with chosen stacks (engine SitAndGo keeps set stacks)."""
    r = random.Random(seed)
    first = r.randrange(n)
    s = Script(n, script)
    table = SitAndGo([s.player() for _ in range(n)], seed=seed,
                     config={"blinds": [[10, 20]], "max_hands": 1, "hands_per_level": 10 ** 9})
    stacks = [2000] * n
    alive_next = lambda b: next((b + k) % n for k in range(1, n + 1)  # noqa: E731
                                if stacks[(b + k) % n] > 0)
    # The engine moves the button to the next alive seat before hand 1.
    button = alive_next(first)
    for off, chips in stack_by_offset.items():
        stacks[(button + off) % n] = chips
    if stacks[button] == 0 or alive_next(first) != button:
        raise AssertionError("pick offsets that keep the button seat alive")
    table.stacks = stacks
    table.play()
    return s.captured


def seat_of(state, off, n):
    return (state["button"] + off) % n


class HandCategory(unittest.TestCase):
    def test_examples(self):
        for hole, cat in ((["As", "Ad"], "AA"), (["Kh", "As"], "AKo"), (["As", "Ks"], "AKs"),
                          (["6s", "7s"], "76s"), (["2c", "7d"], "72o"), (["Td", "Tc"], "TT")):
            self.assertEqual(bot.hand_category(hole), cat)

    def test_all_1326_combos_make_169_classes(self):
        counts = {}
        cards = [r + s for r in bot.RANKS for s in bot.SUITS]
        for i in range(52):
            for j in range(i + 1, 52):
                c = bot.hand_category([cards[i], cards[j]])
                counts[c] = counts.get(c, 0) + 1
        self.assertEqual(len(counts), 169)
        for c, k in counts.items():
            self.assertEqual(k, 6 if len(c) == 2 else 4 if c[2] == "s" else 12, c)


class Positions(unittest.TestCase):
    def test_every_position_with_button_rotation(self):
        for n in (7, 8):
            for button in range(n):
                for me in range(n):
                    state = {"seat": me, "button": button, "stacks": [2000] * n,
                             "folded": [False] * n, "history": []}
                    p = bot.position_info(state)
                    off = (me - button) % n
                    with self.subTest(n=n, button=button, me=me):
                        self.assertEqual(p["label"], LABELS[n][off])
                        self.assertEqual(p["action_order_index"], (off - 3) % n)
                        self.assertEqual(p["original_players_behind"], n - 1 - (off - 3) % n)
                        self.assertEqual(p["players_dealt"], n)

    def test_folds_do_not_relabel(self):
        n = 8
        caps = run_fixed(n, {3: ["fold"], 4: ["fold"], 5: ["call"], 6: ["fold"], 0: ["capture", "fold"]})
        st = caps[0]
        p = bot.position_info(st)
        self.assertEqual(p["label"], "BTN")
        self.assertEqual(p["labels_by_seat"][seat_of(st, 3, n)], "UTG")  # folded, still UTG
        self.assertEqual(p["players_dealt"], 8)

    def test_busted_seat_is_not_dealt(self):
        n = 8
        caps = run_stacks(n, {0: ["capture", "fold"]}, {4: 0})
        p = bot.position_info(caps[0])
        self.assertEqual(p["players_dealt"], 7)
        self.assertEqual(p["label"], "BTN")
        self.assertNotIn(seat_of(caps[0], 4, n), p["seats_in_action_order"])
        self.assertEqual(p["labels_by_seat"][seat_of(caps[0], 3, n)], "UTG")


class PreflopAction(unittest.TestCase):
    def test_unopened(self):
        n = 8
        st = run_fixed(n, {3: ["fold"], 4: ["fold"], 5: ["fold"], 6: ["fold"], 7: ["fold"],
                           0: ["capture", "fold"]})[0]
        a = bot.analyze_preflop(st)["action"]
        self.assertTrue(a["consistent_with_state"])
        self.assertEqual((a["pot_type"], a["limpers"], a["open_raiser"]), ("unopened", [], None))
        self.assertEqual((a["to_call"], a["current_bet"], a["raise_count"]), (20, 20, 0))
        self.assertEqual([b["blind"] for b in a["posted_blinds"]], ["small_blind", "big_blind"])
        self.assertEqual(a["still_to_act_after_us"], [seat_of(st, 1, n), seat_of(st, 2, n)])
        self.assertEqual(a["decision_number"], 1)

    def test_limpers(self):
        n = 8
        st = run_fixed(n, {3: ["call"], 4: ["fold"], 5: ["call"], 6: ["capture", "fold"]})[0]
        a = bot.analyze_preflop(st)["action"]
        self.assertEqual(a["pot_type"], "limped")
        self.assertEqual([l["seat"] for l in a["limpers"]], [seat_of(st, 3, n), seat_of(st, 5, n)])
        self.assertEqual([l["position"] for l in a["limpers"]], ["UTG", "LJ"])
        self.assertTrue(all(not e["voluntary"] for e in a["events"][:2]))
        self.assertTrue(a["events"][2]["voluntary"])

    def test_raise_call_reraise(self):
        n = 8
        st = run_fixed(n, {3: [60], 4: ["fold"], 5: ["call"], 6: ["fold"], 7: [200],
                           0: ["capture", "fold"]})[0]
        a = bot.analyze_preflop(st)["action"]
        self.assertEqual((a["pot_type"], a["raise_count"], a["to_call"]), ("re_raised", 2, 200))
        o = a["open_raiser"]
        self.assertEqual((o["seat"], o["position"], o["raise_to"], o["raise_increment"],
                          o["full_raise"], o["raise_name"]),
                         (seat_of(st, 3, n), "UTG", 60, 40, True, "open_raise"))
        r = a["re_raisers"][0]
        self.assertEqual((r["position"], r["raise_to"], r["raise_increment"], r["raise_name"]),
                         ("CO", 200, 140, "3bet"))
        c = a["callers"][0]
        self.assertEqual((c["position"], c["called_raise_number"], c["amount"]), ("LJ", 1, 60))
        self.assertEqual(a["raises_this_street"], 2)

    def test_repeat_decision_no_duplication(self):
        n = 8
        caps = run_fixed(n, {3: ["capture", "call", "capture", "fold"], 4: ["fold"], 5: ["fold"],
                             6: ["fold"], 7: ["fold"], 0: [100], 1: ["fold"], 2: ["call"]})
        first, second = (bot.analyze_preflop(s)["action"] for s in caps)
        self.assertEqual(first["decision_number"], 1)
        self.assertEqual(second["decision_number"], 2)
        self.assertEqual([x["action"] for x in second["our_previous_actions"]], ["call"])
        self.assertEqual(second["pot_type"], "single_raised")
        self.assertEqual([l["position"] for l in second["limpers"]], ["UTG"])
        self.assertEqual(second["open_raiser"]["position"], "BTN")
        self.assertEqual([c["position"] for c in second["callers"]], ["BB"])
        preflop_events = [e for e in caps[1]["history"] if e["street"] == "preflop"]
        self.assertEqual(len(second["events"]), len(preflop_events))
        self.assertEqual(second["still_to_act_after_us"], [])
        self.assertEqual(second["to_call"], 80)

    def test_short_all_in_raise_does_not_reopen(self):
        n = 8
        caps = run_stacks(n, {3: [60, "capture", "call"], 5: ["call"], 7: ["all_in"],
                              0: ["capture", "fold"]}, {7: 80, 5: 30})
        btn, utg = (bot.analyze_preflop(s)["action"] for s in caps)
        short = btn["re_raisers"][0]
        self.assertEqual((short["position"], short["raise_to"], short["raise_increment"],
                          short["full_raise"], short["all_in"]), ("CO", 80, 20, False, True))
        lj = btn["callers"][0]
        self.assertEqual((lj["position"], lj["amount"], lj["short_call"], lj["all_in"]),
                         ("LJ", 30, True, True))
        self.assertTrue(btn["raising_reopened_for_us"])  # BTN hasn't acted yet
        self.assertTrue(btn["can_raise_now"])
        self.assertFalse(utg["raising_reopened_for_us"])   # UTG already acted
        self.assertFalse(utg["can_raise_now"])
        self.assertEqual(sorted(utg["opponents_all_in"]),
                         sorted([seat_of(caps[1], 5, n), seat_of(caps[1], 7, n)]))
        self.assertTrue(utg["consistent_with_state"])


class MissingHistory(unittest.TestCase):
    def setUp(self):
        self.st = run_fixed(8, {3: [60], 4: ["call"], 5: ["capture", "fold"]})[0]

    def test_no_history(self):
        st = dict(self.st)
        del st["history"]
        out = bot.analyze_preflop(st)
        self.assertFalse(out["action"]["available"])
        self.assertEqual(out["position"]["label"], "LJ")
        self.assertIn("unfolded_seats_only", out["position"]["dealt_seats_source"])

    def test_blinds_missing(self):
        st = dict(self.st, history=self.st["history"][2:])
        self.assertFalse(bot.analyze_preflop(st)["action"]["available"])

    def test_malformed_entry(self):
        st = dict(self.st, history=self.st["history"] + [{"seat": "x", "street": "preflop"}])
        self.assertFalse(bot.analyze_preflop(st)["action"]["available"])

    def test_dropped_event_is_flagged(self):
        st = dict(self.st, history=self.st["history"][:3])  # loses the call
        a = bot.analyze_preflop(st)["action"]
        self.assertFalse(a["consistent_with_state"])
        self.assertIn("warning", a)


class EngineSweep(unittest.TestCase):
    def test_random_play_all_formats(self):
        seen, times = {"pre": 0, "post": 0}, []
        test = self

        class Probe:
            def __init__(self, seed):
                self.rng, self.agent = random.Random(seed), bot.Agent()
                self.labels = {}

            def start_table(self, seat, info):
                self.agent.on_table_start(info)

            def act(self, state):
                t = time.perf_counter()
                out = bot.analyze_preflop(state, self.agent.starting_stack)
                times.append(time.perf_counter() - t)
                a = out["action"]
                test.assertTrue(a["available"])
                key = (state["hand_number"], state["seat"])
                test.assertEqual(self.labels.setdefault(key, out["position"]["label"]),
                                 out["position"]["label"])  # stable within a hand
                if state["street"] == "preflop":
                    seen["pre"] += 1
                    test.assertTrue(a["consistent_with_state"], state)
                    if not a["raising_reopened_for_us"]:
                        test.assertNotIn("raise", state["legal_actions"])
                    ours = [e for e in state["history"] if e["street"] == "preflop"
                            and e["seat"] == state["seat"]
                            and e["action"] not in ("small_blind", "big_blind")]
                    test.assertEqual(a["decision_number"], len(ours) + 1)
                else:
                    seen["post"] += 1
                    test.assertNotIn("to_call", a)
                self.agent.act(state)  # wiring must not raise
                legal = state["legal_actions"]
                choice = self.rng.choice(legal + (["all_in"] if "raise" in legal else []))
                if choice == "raise":
                    lo, hi = state["min_raise_to"], state["max_raise_to"]
                    return {"action": "raise", "amount": self.rng.randint(lo, hi)}
                return {"action": choice}

            def hand_end(self, summary):
                pass

        for seats in (7, 8):
            for betting in ("no_limit", "pot_limit", "fixed_limit"):
                FixedHandsTable([Probe(seats * 10 + i) for i in range(seats)], hands=60, seed=seats,
                                config={"betting": betting, "raise_cap": 3}).play()
        self.assertGreater(seen["pre"], 1000)
        self.assertGreater(seen["post"], 100)
        times.sort()
        print("analyze_preflop: %d calls, mean %.3f ms, p99 %.3f ms, max %.3f ms" % (
            len(times), 1000 * sum(times) / len(times), 1000 * times[int(.99 * len(times))],
            1000 * times[-1]))
        self.assertLess(sum(times) / len(times), 0.001)


if __name__ == "__main__":
    unittest.main(verbosity=2)
