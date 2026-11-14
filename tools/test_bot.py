"""python3 tools/test_bot.py"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

Bot = sim.load(os.path.join(sim.ROOT, "bot.py"))
Baseline = sim.load(os.path.join(sim.ROOT, "tools", "baseline_bot.py"))
EX = os.path.join(sim.ROOT, "kit", "examples")
POOL = [sim.load(os.path.join(EX, f)) for f in sorted(os.listdir(EX)) if f.endswith(".py")]


class Strict(Bot):
    """The bot without act()'s safety net, so a bug shows as an engine error instead of a quiet check-fold."""

    def act(self, state):
        if state["street"] == "preflop":
            return self._preflop(state)
        return self._postflop(state, time.perf_counter())


def _h(seat, street, action, amount=0):
    return {"seat": seat, "street": street, "action": action, "amount": amount}


def _summary(n, history, shown=None):
    return {"hand_number": n, "board": [], "shown": shown or {}, "winners": [], "stacks": [2000, 2000],
            "history": [_h(0, "preflop", "small_blind", 10), _h(1, "preflop", "big_blind", 20)] + history}


def _hand(n, big):
    """Seat 1 calls every bet: a preflop raise (an all-in when `big`), then a flop bet."""
    h = [_h(0, "preflop", "raise", 2000 if big else 100), _h(1, "preflop", "call", 1980 if big else 80)]
    if not big:
        h += [_h(1, "flop", "check"), _h(0, "flop", "raise", 150), _h(1, "flop", "call", 150)]
    return _summary(n, h)


def _preflop_state(hole):
    return {"hole_cards": hole, "board": [], "street": "preflop", "seat": 0, "button": 0,
            "stacks": [1990, 1980], "bets": [10, 20], "folded": [False, False], "pot": 30, "to_call": 10,
            "min_raise_to": 40, "max_raise_to": 2000, "legal_actions": ["fold", "call", "raise"],
            "small_blind": 10, "big_blind": 20, "blind_level": 0, "hand_number": 16, "betting": "no_limit",
            "raise_cap": None, "raises_this_street": 0,
            "history": [_h(0, "preflop", "small_blind", 10), _h(1, "preflop", "big_blind", 20)]}


def _agent(params=None, cls=Bot):
    a = cls(params)
    a.on_table_start({"seat": 0, "num_players": 2, "hands": 1000, "starting_stack": 2000,
                      "stacks_reset_each_hand": True, "small_blind": 10, "big_blind": 20,
                      "betting": "no_limit", "raise_cap": None})
    return a


def _is_big(move):
    return move["action"] == "all_in" or (move["action"] == "raise" and move["amount"] >= 1200)


def test_does_not_shove_an_unopened_pot_against_a_seat_that_calls_everything():
    hole = ["Qs", "Jd"]
    fresh = _agent()
    assert not _is_big(fresh.act(_preflop_state(hole))), "raised big against an unknown seat"
    trained = _agent()
    for n in range(30):
        trained.on_hand_end(_hand(n + 1, big=n % 3 == 0))
    move = trained.act(_preflop_state(hole))
    assert not _is_big(move), move


def test_a_seat_that_called_every_bet_reads_as_a_non_folder():
    a = _agent()
    for n in range(30):
        a.on_hand_end(_hand(n + 1, big=False))
    s = a._seat(1)
    fold = a._rate(s.folds, s.folds + s.continues, a.p["prior_fold"])
    assert fold < 0.15, fold
    assert a._sticky(s) >= 0.8, a._sticky(s)
    assert a._pf_call(s) > 0.8, a._pf_call(s)


def _shows(raise_cards, call_cards, hands=40):
    """Seat 1 in a cycle of four hands: raises and shows `raise_cards`, calls a raise and shows `call_cards`,
    folds to a raise twice."""
    a = _agent()
    checks = [_h(i, st, "check") for st in ("flop", "turn", "river") for i in (1, 0)]
    for n in range(hands):
        k = n % 4
        if k == 0:
            h = [_h(0, "preflop", "call", 10), _h(1, "preflop", "raise", 60), _h(0, "preflop", "call", 40)] + checks
            shown = {"0": ["9h", "8h"], "1": raise_cards}
        elif k == 1:
            h = [_h(0, "preflop", "raise", 60), _h(1, "preflop", "call", 40)] + checks
            shown = {"0": ["9h", "8h"], "1": call_cards}
        else:
            h, shown = [_h(0, "preflop", "raise", 60), _h(1, "preflop", "fold")], None
        a.on_hand_end(_summary(n + 1, h, shown))
    return a


def test_a_seat_whose_raises_show_weak_hands_gets_a_wider_range():
    strategic = _shows(["As", "Ad"], ["Ts", "9s"])
    random_ = _shows(["7d", "2c"], ["Ts", "9s"])
    ws, wr = strategic._raise_width(1, 1, 60), random_._raise_width(1, 1, 60)
    assert wr > 1.5 * ws, (ws, wr)
    assert abs(ws - strategic._rate(strategic._seat(1).pfr, strategic._seat(1).hands, 0.15)) < 1e-9


def thinking(cls, hands, seed, pool=POOL):
    """Seconds of act() plus on_hand_end() for one seat of `cls` against the pool over one deal."""
    clock = [0.0]

    class Timed(cls):
        def act(self, state):
            t = time.thread_time()
            move = cls.act(self, state)
            clock[0] += time.thread_time() - t
            return move

        def on_hand_end(self, summary):
            t = time.thread_time()
            cls.on_hand_end(self, summary)
            clock[0] += time.thread_time() - t

    players = [LocalPlayer(Timed)] + [LocalPlayer(pool[i % len(pool)]) for i in range(7)]
    FixedHandsTable(players, hands=hands, seed=seed).play()
    return clock[0]


def test_thinking_per_hand_stays_within_budget():
    ours = base = 0.0
    for seed in range(4):  # back to back on the same deals in thread CPU time: wall time swung 1.0-1.7x under load
        base += thinking(Baseline, 250, seed)
        ours += thinking(Bot, 250, seed)
    assert ours <= 1.5 * base, (ours, base)
    print("thinking: %.3f s vs baseline %.3f s over 1000 hands, ratio %.2f" % (ours, base, ours / base))


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
