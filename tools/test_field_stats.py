"""field_stats.py must count a hand-made three-hand round exactly as worked out by hand, read simulated rounds the same
way, and a field clone must play a table without errors."""
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "opponents", "field"))
import field_stats as fs  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402
from field_base import make_agent  # noqa: E402


def act(seat, action, amount=0):
    return ["act", seat, action, amount]


HANDS = [
    # C opens, D calls, A folds, B 3-bets from the big blind, C folds, D calls; B c-bets half the pot, D folds.
    {"n": 1, "button": 3, "bb": 20, "hole": {"0": ["7c", "2d"]}, "showdown": {}, "results": [-10, 270, -60, -200],
     "events": [["post", 0, 10], ["post", 1, 20], act(2, "raise", 60), act(3, "call", 60), act(0, "fold"),
                act(1, "raise", 200), act(2, "fold"), act(3, "call", 140), ["board", "flop", ["As", "Kd", "2c"]],
                act(1, "raise", 235), act(3, "fold"), ["refund", 1, 235], ["win", 1, 470, None]]},
    # D limps, A raises to 800, B folds, C calls, D folds; checked down, A's aces beat C's kings.
    {"n": 2, "button": 0, "bb": 20, "hole": {"0": ["Ah", "Ad"], "2": ["Kc", "Ks"]},
     "showdown": {"0": "Pair", "2": "Pair"}, "results": [830, -10, -800, -20],
     "events": [["post", 1, 10], ["post", 2, 20], act(3, "call", 20), act(0, "raise", 800), act(1, "fold"),
                act(2, "call", 780), act(3, "fold"), ["board", "flop", ["2h", "7d", "9s"]], act(2, "check"),
                act(0, "check"), ["board", "turn", ["2h", "7d", "9s", "Tc"]], act(2, "check"), act(0, "check"),
                ["board", "river", ["2h", "7d", "9s", "Tc", "Jd"]], act(2, "check"), act(0, "check"),
                ["win", 0, 1630, "Pair"]]},
    # A opens, D calls from the big blind; A c-bets big, D calls; D bets the pot on the river with a set, A calls ace high.
    {"n": 3, "button": 1, "bb": 20, "hole": {"0": ["Ac", "2c"], "3": ["9h", "9s"]},
     "showdown": {"0": "High Card", "3": "Three of a Kind"}, "results": [-490, 0, -10, 500],
     "events": [["post", 2, 10], ["post", 3, 20], act(0, "raise", 60), act(1, "fold"), act(2, "fold"),
                act(3, "call", 40), ["board", "flop", ["Qs", "8h", "3d"]], act(3, "check"), act(0, "raise", 100),
                act(3, "call", 100), ["board", "turn", ["Qs", "8h", "3d", "4c"]], act(3, "check"), act(0, "check"),
                ["board", "river", ["Qs", "8h", "3d", "4c", "9c"]], act(3, "raise", 330), act(0, "call", 330),
                ["win", 3, 990, "Three of a Kind"]]},
]

EXPECTED = {
    "A": {"hands": 3, "vpip": 2, "pfr": 2, "shove": 1, "unraised": 2, "limp": 0, "faced_open": 1, "threebet": 0,
          "cbet_opp": 2, "cbet": 1, "checked_to_flop": 2, "bet_flop": 1, "checked_to_turn": 2, "checked_to_river": 1,
          "faced_bet": 1, "faced_pot": 1, "fold": 0, "post_aggr": 1, "post_call": 1, "saw_flop": 2, "showdown": 2,
          "big_sd": 1, "big_sd_strong": 0, "hands_CO": 1, "pfr_CO": 1, "hands_BTN": 1, "pfr_BTN": 1, "hands_SB": 1},
    "B": {"hands": 3, "vpip": 1, "pfr": 1, "faced_open": 3, "threebet": 1, "faced_allin": 1, "call_allin": 0,
          "cbet_opp": 1, "cbet": 1, "bet_flop": 1, "sized": 1, "big": 0, "saw_flop": 1, "showdown": 0},
    "C": {"hands": 3, "vpip": 2, "pfr": 1, "unraised": 1, "faced_3bet": 1, "fold_3bet": 1, "faced_allin": 1,
          "call_allin": 1, "faced_open": 2, "call_open": 1, "checked_to_flop": 1, "bet_flop": 0, "showdown": 1},
    "D": {"hands": 3, "vpip": 3, "pfr": 0, "unraised": 1, "limp": 1, "faced_open": 3, "call_open": 2,
          "faced_allin": 1, "call_allin": 0, "faced_bet": 2, "faced_medium": 2, "fold": 1, "fold_flop": 1,
          "checked_to_river": 1, "bet_river": 1, "sized": 1, "big": 1, "big_sd": 1, "big_sd_strong": 1, "saw_flop": 2},
}

with tempfile.TemporaryDirectory() as tmp:
    path = os.path.join(tmp, "saturday_r007.json")
    with open(path, "w") as f:
        json.dump({"ref": "saturday/r007", "seat": 0, "players": ["A", "B", "C", "D"], "hands": HANDS,
                   "round": {"ref": "saturday/r007", "seat": 0}}, f)
    rounds = fs.load_rounds(path)
    assert len(rounds) == 1 and fs.load_rounds(path, first=8) == [], "round-number filter"
    teams = fs.by_team(rounds)
    for team, want in EXPECTED.items():
        got = {k: teams[team]["c"][k] for k in want}
        assert got == want, "%s: %s" % (team, {k: (got[k], v) for k, v in want.items() if got[k] != v})
    assert teams["A"]["c"]["won_bb"] == 16.5 and teams["A"]["c"]["sd_bb"] == 17.0, "A's chips by showdown"
    assert teams["B"]["sizes"]["flop"] == [0.5] and teams["D"]["sizes"]["river"] == [1.0], "bet sizes"
    r = fs.rates(teams["A"])
    assert r["vpip"] == 2 / 3 and r["cbet"] == 0.5 and r["af"] == 1.0 and r["big_strong"] == 0.0, r

    # A simulated round read through from_log counts the same way and shows only what the site would show.
    clone = make_agent({"open_BTN": 0.5, "call_margin": 0.1})
    players = [LocalPlayer(clone) for _ in range(6)]
    log = FixedHandsTable(players, hands=150, seed=5, record=True).play()["log"]
    errors = [p.stats.error_samples[0] for p in players if p.stats.errors]
    assert not errors, errors[0]
    rnd = fs.from_log(log, list("abcdef"), seat=0)
    for h, rec in zip(rnd["hands"], log):
        assert set(h["hole"]) == {0} | {int(s) for s in rec.get("showdown", {})}, "hole cards beyond showdown"
        assert sum(h["results"]) == 0
    sim = fs.by_team([(rnd, fs.walk(rnd))])
    assert all(sim[n]["c"]["hands"] == 150 for n in "abcdef")
    assert all(0 <= v <= 1 for t in sim.values() for k, v in fs.rates(t).items()
               if v is not None and k in fs.RATES), "rates are shares"
print("field_stats ok")
