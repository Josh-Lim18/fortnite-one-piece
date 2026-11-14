import importlib.util
import os
import random
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("bot_under_test", os.path.join(ROOT, "bot.py"))
bot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bot)

SEATS = 8
EMPTY_RANGE = -1.0
LOOSE_RAISER_HANDS, LOOSE_RAISER_RAISES = 200, 120


def _agent(**params):
    a = bot.Agent(params=params or None)
    a.on_table_start({"num_players": SEATS, "starting_stack": 2000, "big_blind": 20})
    a.rng = random.Random(1)
    return a


def _cards(text):
    return [bot.card(c) for c in text.split()]


def _blinds(sb, bb):
    return [{"seat": sb, "street": "preflop", "action": "small_blind", "amount": 10},
            {"seat": bb, "street": "preflop", "action": "big_blind", "amount": 20}]


def _preflop(hole, me, history, bets):
    """Button 0, blinds 1 and 2; `bets` maps seat to chips in front."""
    row = [bets.get(i, 0) for i in range(SEATS)]
    return {"hole_cards": hole, "board": [], "street": "preflop", "seat": me, "button": 0,
            "stacks": [2000 - b for b in row], "bets": row, "folded": [False] * SEATS,
            "pot": sum(row), "to_call": max(row) - row[me], "min_raise_to": max(row) * 2,
            "max_raise_to": 2000, "legal_actions": ["fold", "call", "raise"], "big_blind": 20,
            "history": history}


def _rejection_equity(hero, board, widths, samples, rng):
    """Plain rejection sampling: only deals with every opponent inside its range are counted."""
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


def test_equity_matches_rejection_sampling():
    hero, board, widths = _cards("Ks Qd"), _cards("Kh 7c 2d"), [0.15, 0.15]
    a = _agent(trials=3000, decision_ms=10_000, round_budget_s=1e9, round_stop_s=1e9)
    got = a._equity(hero, board, widths, time.perf_counter())
    ref = _rejection_equity(hero, board, widths, 3000, random.Random(2))
    assert abs(got - ref) < 0.04, (got, ref)


def _joint_equity(hero, board, widths, samples, rng):
    """Exact joint deal: each opponent uniform over its range, any clash rejects the whole deal."""
    ranges = [[(a, b) for a in range(52) for b in range(a + 1, 52) if bot.hand_pct(a, b) <= w] for w in widths]
    used = set(hero) | set(board)
    missing = 5 - len(board)
    won = n = 0
    while n < samples:
        hands = [list(rng.choice(r)) for r in ranges]
        cards = [c for h in hands for c in h]
        if len(set(cards)) < len(cards) or used & set(cards):
            continue
        rest = [c for c in range(52) if c not in used and c not in cards]
        full = board + rng.sample(rest, missing)
        mine = bot.score(hero + full)
        best = max(bot.score(h + full) for h in hands)
        won += 1.0 if mine > best else 0.5 if mine == best else 0.0
        n += 1
    return won / n


def test_equity_matches_the_joint_deal_with_three_narrow_ranges():
    hero, board, widths = _cards("9d 9c"), _cards("9h Ac Ks"), [0.08, 0.08, 0.08]
    a = _agent(trials=8000, decision_ms=60_000, round_budget_s=1e9, round_stop_s=1e9)
    got = a._equity(hero, board, widths, time.perf_counter())
    ref = _joint_equity(hero, board, widths, 8000, random.Random(3))
    assert abs(got - ref) < 0.02, (got, ref)


def test_equity_runs_trials_even_when_the_deadline_has_passed():
    a = _agent()
    hero, board = _cards("As Ah"), _cards("Ac Ad 2c 7h 9s")  # quad aces on a board with no straight flush
    assert a._equity(hero, board, [0.3, 0.3], time.perf_counter() - 1.0) == 1.0


def test_equity_does_not_starve_with_three_tight_ranges_at_shipped_settings():
    a = _agent()
    hero, board = _cards("7s 2d"), _cards("Kh Qc Jd")
    for _ in range(50):
        eq = a._equity(hero, board, [0.15, 0.15, 0.15], time.perf_counter())
        assert eq < 0.2, eq


def test_equity_is_neutral_only_when_a_range_is_empty():
    a = _agent(trials=20)
    assert a._equity(_cards("As Ah"), _cards("2c 7d 9h"), [EMPTY_RANGE], time.perf_counter()) == 0.5


def _stations(a, seats):
    for i in seats:
        s = a._seat(i)
        s.hands, s.pf_faced, s.pf_called, s.shove_faced, s.shove_called = 200, 50, 50, 50, 50


def test_no_value_shove_in_an_unopened_pot():
    a = _agent()
    _stations(a, [s for s in range(SEATS) if s != 3])
    move = a.act(_preflop(["As", "Ah"], 3, _blinds(1, 2), {1: 10, 2: 20}))
    assert move["action"] == "raise" and move["amount"] < 2000, move


def test_value_shove_still_fires_against_a_raise():
    a = _agent()
    _stations(a, [s for s in range(SEATS) if s != 4])
    hist = _blinds(1, 2) + [{"seat": 3, "street": "preflop", "action": "raise", "amount": 60}]
    assert a.act(_preflop(["As", "Ah"], 4, hist, {1: 10, 2: 20, 3: 60})) == {"action": "raise", "amount": 2000}


def test_calls_a_cheap_raise_from_a_loose_raiser_inside_call_cap():
    a = _agent()
    raiser = a._seat(0)
    raiser.hands, raiser.pfr = LOOSE_RAISER_HANDS, LOOSE_RAISER_RAISES
    hist = _blinds(1, 2) + [{"seat": 0, "street": "preflop", "action": "raise", "amount": 60}]
    hand = ["Ts", "8s"]
    assert bot.hand_pct(*(bot.card(c) for c in hand)) < a.p["call_cap"]
    assert a.act(_preflop(hand, 2, hist, {0: 60, 1: 10, 2: 20})) == {"action": "call"}


def test_folds_a_hand_outside_call_cap_to_the_same_raise():
    a = _agent()
    raiser = a._seat(0)
    raiser.hands, raiser.pfr = LOOSE_RAISER_HANDS, LOOSE_RAISER_RAISES
    hist = _blinds(1, 2) + [{"seat": 0, "street": "preflop", "action": "raise", "amount": 60}]
    hand = ["8d", "6d"]
    assert bot.hand_pct(*(bot.card(c) for c in hand)) > a.p["call_cap"]
    assert a.act(_preflop(hand, 2, hist, {0: 60, 1: 10, 2: 20})) == {"action": "fold"}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
