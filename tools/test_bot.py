"""python3 tools/test_bot.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

Bot = sim.load(os.path.join(sim.ROOT, "bot.py"))
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


def _agent():
    a = Bot()
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
