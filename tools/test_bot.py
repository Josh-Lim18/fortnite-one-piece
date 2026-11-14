"""python3 tools/test_bot.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

Bot = sim.load(os.path.join(sim.ROOT, "bot.py"))
BOT = sys.modules[Bot.__module__]
EX = os.path.join(sim.ROOT, "kit", "examples")
POOL = [sim.load(os.path.join(EX, f)) for f in sorted(os.listdir(EX)) if f.endswith(".py")]


class Strict(Bot):
    """The bot without act()'s safety net, so a bug shows as an engine error instead of a quiet check-fold."""

    def act(self, state):
        if state["street"] == "preflop":
            return self._preflop(state)
        return self._postflop(state, time.perf_counter())


def _hand(n, big):
    """Seat 1 calls every bet: a preflop raise (an all-in when `big`), then a flop bet."""
    h = [{"seat": 0, "street": "preflop", "action": "small_blind", "amount": 10},
         {"seat": 1, "street": "preflop", "action": "big_blind", "amount": 20},
         {"seat": 0, "street": "preflop", "action": "raise", "amount": 2000 if big else 100},
         {"seat": 1, "street": "preflop", "action": "call", "amount": 1980 if big else 80}]
    if not big:
        h += [{"seat": 1, "street": "flop", "action": "check", "amount": 0},
              {"seat": 0, "street": "flop", "action": "raise", "amount": 150},
              {"seat": 1, "street": "flop", "action": "call", "amount": 150}]
    return {"hand_number": n, "board": [], "shown": {}, "winners": [], "stacks": [2000, 2000], "history": h}


def _preflop_state(hole):
    return {"hole_cards": hole, "board": [], "street": "preflop", "seat": 0, "button": 0,
            "stacks": [1990, 1980], "bets": [10, 20], "folded": [False, False], "pot": 30, "to_call": 10,
            "min_raise_to": 40, "max_raise_to": 2000, "legal_actions": ["fold", "call", "raise"],
            "small_blind": 10, "big_blind": 20, "blind_level": 0, "hand_number": 16, "betting": "no_limit",
            "raise_cap": None, "raises_this_street": 0,
            "history": [{"seat": 0, "street": "preflop", "action": "small_blind", "amount": 10},
                        {"seat": 1, "street": "preflop", "action": "big_blind", "amount": 20}]}


def _flop_state(hole, board):
    """Heads-up flop checked to us; we raised preflop and seat 1 called."""
    return {"hole_cards": hole, "board": board, "street": "flop", "seat": 0, "button": 0,
            "stacks": [1930, 1930], "bets": [0, 0], "folded": [False, False], "pot": 140, "to_call": 0,
            "min_raise_to": 20, "max_raise_to": 1930, "legal_actions": ["check", "raise"],
            "small_blind": 10, "big_blind": 20, "blind_level": 0, "hand_number": 16, "betting": "no_limit",
            "raise_cap": None, "raises_this_street": 0,
            "history": [{"seat": 0, "street": "preflop", "action": "small_blind", "amount": 10},
                        {"seat": 1, "street": "preflop", "action": "big_blind", "amount": 20},
                        {"seat": 0, "street": "preflop", "action": "raise", "amount": 70},
                        {"seat": 1, "street": "preflop", "action": "call", "amount": 50}]}


def _agent(params=None):
    a = Bot(params)
    a.on_table_start({"seat": 0, "num_players": 2, "hands": 1000, "starting_stack": 2000,
                      "stacks_reset_each_hand": True, "small_blind": 10, "big_blind": 20,
                      "betting": "no_limit", "raise_cap": None})
    return a


def _is_big(move):
    return move["action"] == "all_in" or (move["action"] == "raise" and move["amount"] >= 1200)


def test_presses_a_seat_that_calls_everything():
    hole = ["Qs", "Jd"]
    fresh = _agent()
    assert not _is_big(fresh.act(_preflop_state(hole))), "raised big against an unknown seat"
    trained = _agent()
    for n in range(15):
        trained.on_hand_end(_hand(n + 1, big=n % 3 == 0))
    move = trained.act(_preflop_state(hole))
    assert _is_big(move), move


def test_bet_sizes_jitter_within_ten_percent_and_stay_legal():
    a = _agent()
    state = _flop_state(["As", "Ah"], ["Ad", "7c", "2h"])
    sizes = [a._raise(state, 300)["amount"] for _ in range(500)]
    assert all(270 <= s <= 330 for s in sizes) and len(set(sizes)) > 30, (min(sizes), max(sizes))
    assert a._raise(state, 5)["amount"] == 20, "min raise jittered"
    assert a._raise(state, 1500)["amount"] == 1930, "all-in jittered"


def test_bluffs_and_value_bets_share_a_size():
    a = _agent({"size_jitter": 0.0, "mix_band": 0.0, "bluff_freq": 1.0})
    a.seats[1].folds = 40  # a seat that folds to most bets gets bluffed
    value = Strict.act(a, _flop_state(["As", "Ah"], ["Ad", "7c", "2h"]))
    bluff = Strict.act(a, _flop_state(["6s", "3d"], ["Ad", "Kc", "Th"]))
    assert value["action"] == bluff["action"] == "raise", (value, bluff)
    assert value["amount"] == bluff["amount"], (value, bluff)


def test_mixes_only_near_a_threshold():
    hole = ["Qs", "Jd"]
    pct = BOT.hand_pct(*(BOT.card(c) for c in hole))

    def raises(limit):
        a = _agent({"iso_raise": limit})
        return {a.act(_preflop_state(hole))["action"] == "raise" for _ in range(200)}

    assert raises(pct) == {True, False}, "no mixing exactly at the threshold"
    assert raises(pct + 0.1) == {True}
    assert raises(0.0) == {False}


def test_other_structures_play_clean():
    for betting in ("pot_limit", "fixed_limit"):
        players = [LocalPlayer(Strict)] + [LocalPlayer(POOL[i % len(POOL)]) for i in range(5)]
        FixedHandsTable(players, hands=150, config={"betting": betting}, seed=11).play()
        assert players[0].stats.errors == 0, (betting, players[0].stats.error_samples[:1])


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
