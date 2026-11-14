"""Tests for candidates/improved/bot.py hand and draw analysis.

Run: python candidates/improved/tests/test_analysis.py
The official starter kit is the independent reference. It is looked for at
<repo>/kit (lane A's snapshot) or the KIT environment variable.
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
BOT_PATH = HERE.parent / "bot.py"
REPO = HERE.parents[2]
KIT = Path(os.environ.get("KIT", REPO / "kit"))

spec = importlib.util.spec_from_file_location("lane_c_bot", BOT_PATH)
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)

HAVE_KIT = (KIT / "engine" / "cards.py").is_file()
if HAVE_KIT:
    sys.path.insert(0, str(KIT))
    from engine import cards as ref  # noqa: E402

NEED_KIT = unittest.skipUnless(HAVE_KIT, "official kit not found; set KIT=path")


def C(text):
    return text.split()


def hand(hole, board):
    return bot.analyze(C(hole), C(board))["hand"]


def draws(hole, board):
    return bot.analyze(C(hole), C(board))["draws"]


def by_type(d, kind, group="direct"):
    found = [x for x in d[group] if x["type"] == kind]
    assert len(found) == 1, (kind, d)
    return found[0]


class RankingAgainstEngine(unittest.TestCase):
    @NEED_KIT
    def test_random_hands_match_engine(self):
        rng = random.Random(20261114)
        for size in (5, 6, 7):
            for _ in range(15000):
                cards = rng.sample(range(52), size)
                ours = bot.best_five(cards[:2], cards[2:])[0]
                self.assertEqual(ours, ref.evaluate(cards), [bot.card_str(c) for c in cards])

    @NEED_KIT
    def test_named_edge_hands_match_engine(self):
        cases = [
            "Ac 2d 3h 4s 5c Kd Qh",   # wheel
            "Ac 2c 3c 4c 5c Kd Qh",   # steel wheel
            "Ac Kd Qh Js Tc 2d 3h",   # broadway
            "6c 2d 3h 4s 5c Ad Kh",   # six-high beats the wheel
            "Ah Kh 9h 4h 2h 3h Qd",   # six hearts: best five kickers
            "As Ah Ad Ks Kh Kc 2d",   # two trips -> full house, trips aces
            "As Ah Ks Kh Qd Qc Js",   # three pairs -> two pair, best kicker Q
            "As Ah Ad Ac Kd Qh 2h",   # quads, king kicker
            "9s 9h 9d 9c Kd Kh 2h",   # quads with a pair: king kicker
            "Ts Js Qs Ks As 9s 8s",   # royal flush over a lower straight flush
            "2h 3h 4h 5h 6d 7h 8c",   # flush beats straight on the same cards
        ]
        for text in cases:
            cards = [bot.card_int(c) for c in C(text)]
            with self.subTest(text):
                self.assertEqual(bot.best_five(cards[:2], cards[2:])[0], ref.evaluate(cards))


class MadeHands(unittest.TestCase):
    def test_categories_and_kickers(self):
        h = hand("Ac 2d", "3h 4s 5c Kd Qh")
        self.assertEqual((h["category_name"], h["score"]), ("straight", (4, 3)))
        h = hand("Ah 9h", "Kh 4h 2h 3c Qd")
        self.assertEqual(h["score"], (5, 12, 11, 7, 2, 0))  # A K 9 4 2 of hearts
        h = hand("As Ks", "Ah Kh Qd Qc Js")
        self.assertEqual(h["score"], (2, 12, 11, 10))

    def test_plays_the_board_on_the_river(self):
        h = hand("2c 3d", "Ac Kd Qh Js Th")
        self.assertTrue(h["plays_board"])
        self.assertEqual((h["hole_cards_used"], h["hole_contribution"]), (0, "none_plays_board"))
        h = hand("9c 2d", "Ac Kd Qh Js Th")  # 9 doesn't improve broadway
        self.assertTrue(h["plays_board"])
        h = hand("Ac 2d", "Kc Kd Qh Qs 3h")  # ace kicker plays
        self.assertFalse(h["plays_board"])
        self.assertEqual(h["hole_contribution"], "kicker_only")

    def test_no_plays_board_before_river(self):
        self.assertFalse(hand("2c 3d", "Ac Kd Qh Js")["plays_board"])

    def test_board_vs_hole_strength(self):
        h = hand("Ac 2d", "7h 7s Kc")  # board pair, our cards only kick
        self.assertEqual((h["category_name"], h["board_category_name"], h["hole_contribution"]),
                         ("pair", "pair", "kicker_only"))
        self.assertTrue(h["board_paired"])
        self.assertEqual(h["pairs_with_hole_cards"], [])
        h = hand("Ks 2d", "7h 7s Kc")  # two pair, one pair from our king
        self.assertEqual((h["category_name"], h["hole_contribution"]),
                         ("two_pair", "improves_board_category"))
        self.assertEqual(h["pairs_with_hole_cards"][0]["type"], "top_pair")

    def test_pair_classes(self):
        cases = [
            ("Qc Qd", "Jh 7s 2c", "overpair"),
            ("3c 3d", "Jh 7s 5c", "underpair"),
            ("9c 9d", "Jh 7s 2c", "pocket_pair_between_board_ranks"),
            ("Jc Ad", "Jh 7s 2c", "top_pair"),
            ("7c Ad", "Jh 7s 2c", "middle_pair"),
            ("2d Ad", "Jh 7s 2c", "bottom_pair"),
        ]
        for hole, board, label in cases:
            with self.subTest(hole=hole):
                pairs = hand(hole, board)["pairs_with_hole_cards"]
                self.assertEqual(pairs[0]["type"], label)
        top = hand("Jc Ad", "Jh 7s 2c")["pairs_with_hole_cards"][0]
        self.assertEqual(top["kicker"], "A")
        self.assertEqual(hand("7c 7d", "Jh 7s 2c")["pairs_with_hole_cards"], [])  # a set


class Draws(unittest.TestCase):
    def test_two_card_flush_draw(self):
        d = draws("Ah Kh", "7h 2h 9c")
        f = by_type(d, "flush_draw")
        self.assertEqual((f["outs"], f["hole_cards_in_suit"]), (9, 2))
        self.assertAlmostEqual(f["next_card"], 9 / 47)
        self.assertAlmostEqual(f["by_river"], 1 - (38 / 47) * (37 / 46))
        self.assertNotIn("Ah", d["combined_direct_outs"])

    def test_open_ended(self):
        d = draws("8c 9d", "7h 6s 2c")
        s = by_type(d, "open_ended")
        self.assertEqual((sorted(s["completing_ranks"]), s["outs"]), (["5", "T"], 8))
        self.assertAlmostEqual(s["by_river"], 1 - (39 / 47) * (38 / 46))

    def test_gutshot_and_double_gutshot(self):
        self.assertEqual(by_type(draws("9c 8d", "6h 5s 2c"), "gutshot")["completing_ranks"], ["7"])
        dg = by_type(draws("9c 7d", "Jh 8s 5c"), "double_gutshot")
        self.assertEqual((sorted(dg["completing_ranks"]), dg["outs"]), (["6", "T"], 8))

    def test_ace_low_draws(self):
        self.assertEqual(by_type(draws("Ac 2d", "3h 4s 9c"), "gutshot")["completing_ranks"], ["5"])
        oe = by_type(draws("2c 3d", "4h 5s Kc"), "open_ended")
        self.assertEqual((sorted(oe["completing_ranks"]), oe["outs"]), (["6", "A"], 8))

    def test_combo_draw_counts_overlap_once(self):
        d = draws("9h 8h", "7h 6c 2h")
        self.assertEqual(by_type(d, "flush_draw")["outs"], 9)
        self.assertEqual(by_type(d, "open_ended")["outs"], 8)
        self.assertEqual(d["combined"]["outs"], 15)  # Th and 5h counted once
        self.assertAlmostEqual(d["combined"]["by_river"], 1 - (32 / 47) * (31 / 46))

    def test_turn_probabilities(self):
        d = draws("Ah Kh", "7h 2h 9c 3d")
        f = by_type(d, "flush_draw")
        self.assertAlmostEqual(f["next_card"], 9 / 46)
        self.assertNotIn("by_river", f)
        self.assertEqual(d["backdoor"], [])

    def test_shared_board_draws_are_not_direct(self):
        d = draws("Ac Kd", "5h 9h Jh 2h")  # four hearts on board, none in hand
        self.assertEqual(by_type(d, "flush_draw", "shared_board")["outs"], 9)
        self.assertEqual(d["direct"], [])
        d = draws("Ac Kd", "5h 6c 7s 8d")  # board is four to a straight
        s = by_type(d, "board_straight_draw", "shared_board")
        self.assertEqual(sorted(s["completing_ranks"]), ["4", "9"])
        self.assertEqual(d["combined"]["outs"], 0)

    def test_hole_card_beats_board_straight(self):
        d = draws("Tc 2d", "5h 6c 7s 8d")  # 9 gives us 6-T, board only 5-9
        mine = by_type(d, "gutshot")
        self.assertEqual(mine["completing_ranks"], ["9"])
        self.assertEqual(by_type(d, "board_straight_draw", "shared_board")["completing_ranks"], ["4"])

    def test_backdoors(self):
        d = draws("Ah Kh", "7h 2c 9d")
        bf = by_type(d, "backdoor_flush", "backdoor")
        self.assertAlmostEqual(bf["probability_by_river"], 10 * 9 / (47 * 46))
        d = draws("9c 8d", "7h 2s Kc")
        bs = by_type(d, "backdoor_straight", "backdoor")
        self.assertEqual(sorted(bs["rank_pairs"]), ["56", "6T", "TJ"])
        self.assertAlmostEqual(bs["probability_by_river"], 3 * 2 * 4 * 4 / (47 * 46))
        self.assertEqual(d["combined"]["outs"], 0)  # backdoors aren't direct outs

    def test_no_draws_on_river_or_when_made(self):
        self.assertFalse(draws("Ah Kh", "7h 2h 9c 3d 4s")["applicable"])
        d = draws("Ah Kh", "7h 2h 9h")  # already a flush
        self.assertTrue(d["has_flush"])
        self.assertEqual([x for x in d["direct"] if x["type"] == "flush_draw"], [])


class Integration(unittest.TestCase):
    @NEED_KIT
    def test_fallback_matches_starter_on_engine_states(self):
        sys.path.insert(0, str(KIT))
        from engine import FixedHandsTable
        starter_spec = importlib.util.spec_from_file_location("kit_starter", KIT / "bot.py")
        starter = importlib.util.module_from_spec(starter_spec)
        starter_spec.loader.exec_module(starter)
        seen = {"n": 0, "streets": set()}
        test = self

        class Probe:
            def __init__(self, seed):
                self.ours, self.ref = bot.Agent(), starter.Agent()
                self.rng = random.Random(seed)

            def start_table(self, seat, info):
                self.ours.on_table_start(info)
                self.ref.on_table_start(info)

            def act(self, state):
                mine = self.ours.act(state)
                test.assertEqual(mine, self.ref.act(state))
                bot.analyze(state["hole_cards"], state["board"])  # must not raise
                seen["n"] += 1
                seen["streets"].add(state["street"])
                choice = self.rng.choice(state["legal_actions"])
                if choice == "raise":
                    return {"action": "raise", "amount": state["min_raise_to"]}
                return {"action": choice}

            def hand_end(self, summary):
                self.ours.on_hand_end(summary)

        for seats in (7, 8):
            for betting in ("no_limit", "pot_limit", "fixed_limit"):
                players = [Probe(100 * seats + i) for i in range(seats)]
                FixedHandsTable(players, hands=40, seed=77,
                                config={"betting": betting, "raise_cap": 3}).play()
        self.assertGreater(seen["n"], 1000)
        self.assertEqual(seen["streets"], {"preflop", "flop", "turn", "river"})

    def test_analysis_runtime(self):
        rng = random.Random(5)
        for board_size, limit_ms in ((3, 1.0), (4, 1.0), (5, 1.0)):
            samples = []
            for _ in range(2000):
                cards = [bot.card_str(c) for c in rng.sample(range(52), 2 + board_size)]
                t = time.perf_counter()
                bot.analyze(cards[:2], cards[2:])
                samples.append((time.perf_counter() - t) * 1000)
            samples.sort()
            mean = sum(samples) / len(samples)
            print("board=%d mean=%.3fms p99=%.3fms max=%.3fms"
                  % (board_size, mean, samples[int(0.99 * len(samples))], samples[-1]))
            self.assertLess(mean, limit_ms)

    def test_packaging(self):
        source = BOT_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source, feature_version=(3, 12))
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)
                 for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree)
                  if isinstance(n, ast.ImportFrom) and n.module}
        self.assertTrue(names <= set(sys.stdlib_module_names), names)
        self.assertTrue(any(isinstance(n, ast.ClassDef) and n.name == "Agent" for n in tree.body))
        size = BOT_PATH.stat().st_size
        print("bot.py size: %d bytes" % size)
        self.assertLess(size, 200_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
