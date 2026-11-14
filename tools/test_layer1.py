"""python3 tools/test_layer1.py"""
import importlib.util
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("bot_under_test", os.path.join(ROOT, "bot.py"))
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)


def _agent(**params):
    a = bot.Agent(params=params or None)
    a.on_table_start({"num_players": 8, "starting_stack": 2000, "big_blind": 20})
    a.rng = random.Random(1)
    return a


def _preflop(hole, history, bets, me, button, to_call):
    n = 8
    return {"hole_cards": hole, "board": [], "street": "preflop", "seat": me, "button": button,
            "stacks": [2000 - b for b in bets], "bets": bets, "folded": [False] * n,
            "pot": sum(bets), "to_call": to_call, "min_raise_to": max(bets) * 2,
            "max_raise_to": 2000, "legal_actions": ["fold", "call", "raise"], "big_blind": 20,
            "history": history}


def _blinds(sb, bb):
    return [{"seat": sb, "street": "preflop", "action": "small_blind", "amount": 10},
            {"seat": bb, "street": "preflop", "action": "big_blind", "amount": 20}]


def _reference_equity(hero, board, widths, samples, rng):
    """Independent check: plain rejection sampling, only in-range deals counted."""
    used = set(hero) | set(board)
    deck = [c for c in range(52) if c not in used]
    missing = 5 - len(board)
    won = n = 0
    while n < samples:
        d = rng.sample(deck, missing + 2 * len(widths))
        opp = [d[missing + 2 * i: missing + 2 * i + 2] for i in range(len(widths))]
        if any(bot.hand_pct(o[0], o[1]) > w for o, w in zip(opp, widths)):
            continue
        full = board + d[:missing]
        mine = bot.score(hero + full)
        best = max(bot.score(o + full) for o in opp)
        won += 1.0 if mine > best else 0.5 if mine == best else 0.0
        n += 1
    return won / n


def test_equity_counts_only_hands_inside_the_ranges():
    hero = [bot.card("Ks"), bot.card("Qd")]
    board = [bot.card("Kh"), bot.card("7c"), bot.card("2d")]
    widths = [0.15, 0.15]
    a = _agent(trials=3000, decision_ms=10_000, round_budget_s=1e9, round_stop_s=1e9, redraws=200)
    got = a._equity(hero, board, widths, 0.0 + __import__("time").perf_counter())
    ref = _reference_equity(hero, board, widths, 3000, random.Random(2))
    assert abs(got - ref) < 0.04, (got, ref)


def test_equity_returns_half_when_no_deal_fits():
    a = _agent(trials=20, redraws=1)
    hero = [bot.card("As"), bot.card("Ah")]
    # A width no hand can fall inside: every trial is skipped, never counted.
    assert a._equity(hero, [bot.card("2c"), bot.card("7d"), bot.card("9h")], [-1.0],
                     __import__("time").perf_counter()) == 0.5


def _station(a, seats):
    for i in seats:
        s = a._seat(i)
        s.hands, s.pf_faced, s.pf_called, s.shove_faced, s.shove_called = 200, 50, 50, 50, 50


def test_no_value_shove_in_an_unopened_pot():
    a = _agent()
    _station(a, range(1, 8))
    # Seat 3 is first to act (button 0, blinds 1 and 2) with aces against seven callers of everything.
    st = _preflop(["As", "Ah"], _blinds(1, 2), [0, 10, 20, 0, 0, 0, 0, 0], me=3, button=0, to_call=20)
    move = a.act(st)
    assert move["action"] == "raise" and move["amount"] < 2000, move


def test_value_shove_still_fires_against_a_raise():
    a = _agent()
    _station(a, range(1, 8))
    hist = _blinds(1, 2) + [{"seat": 3, "street": "preflop", "action": "raise", "amount": 60}]
    st = _preflop(["As", "Ah"], hist, [0, 10, 20, 60, 0, 0, 0, 0], me=4, button=0, to_call=60)
    assert a.act(st) == {"action": "raise", "amount": 2000}


def test_calls_a_cheap_raise_with_a_hand_between_the_old_and_new_cap():
    a = _agent()
    raiser = a._seat(0)
    raiser.hands, raiser.pfr = 200, 120  # raises 60% of hands
    hist = _blinds(1, 2) + [{"seat": 0, "street": "preflop", "action": "raise", "amount": 60}]
    # Ts8s ranks about 0.30: inside the 0.40 cap, outside the old 0.22.
    st = _preflop(["Ts", "8s"], hist, [60, 10, 20, 0, 0, 0, 0, 0], me=2, button=0, to_call=40)
    assert a.act(st) == {"action": "call"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
