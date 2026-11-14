"""advitrocks9's decide(): short-stack push/fold, then the network, then an engine action.

Works in Fullhouse units (100-chip big blind) on a Fullhouse-format game_state, exactly
like the original bot/bot.py, except that seats 7-8 at 7-8-player tables count as "CO"
(the original raised IndexError there and fell back to check/call).
"""

from advit_lite.features import BIG_BLIND, encode_state, infer_dealer
from advit_lite.network import strategy

FOLD, CHECK_CALL, BET_50, BET_POT, ALL_IN = range(5)
_RANK_VAL = {r: i for i, r in enumerate("23456789TJQKA")}
_POSITIONS_6MAX = ("BTN", "SB", "BB", "LJ", "HJ", "CO")

_PF_TIER1 = set("AA KK QQ JJ TT 99 88 77 AKs AKo AQs AQo AJs ATs AJo KQs KJs KQo ATo A9s A8s A7s "
                "A6s A5s A4s A3s A2s".split())
_PF_TIER2 = _PF_TIER1 | set("66 55 44 33 22 KTs K9s K8s QJs QTs Q9s JTs J9s T9s T8s 98s 87s 76s KJo KTo "
                            "QJo QTo JTo A9o A8o".split())
_PF_TIER3 = _PF_TIER2 | set("K7s K6s K5s K4s K3s K2s Q8s Q7s Q6s J8s J7s T7s 97s 86s 75s 65s 54s K9o K8o "
                            "Q9o J9o T9o 98o 87o A7o A6o A5o A4o A3o A2o".split())
_PF_CALL_TIGHT = set("AA KK QQ JJ TT 99 88 77 AKs AKo AQs AQo AJs ATs A9s KQs KJs KTs QJs".split())
_PF_CALL_MEDIUM = _PF_CALL_TIGHT | set("66 55 44 AJo ATo A8s A7s A6s A5s KQo KJo QTs JTs T9s".split())
_PF_CALL_WIDE = _PF_CALL_MEDIUM | set("33 22 A4s A3s A2s K9s QJo Q9s J9s A9o A8o A7o".split())


def hand_class(cards):
    r0, s0, r1, s1 = cards[0][0], cards[0][1], cards[1][0], cards[1][1]
    if _RANK_VAL[r0] < _RANK_VAL[r1]:
        r0, r1, s0, s1 = r1, r0, s1, s0
    if r0 == r1:
        return r0 + r1
    return r0 + r1 + ("s" if s0 == s1 else "o")


def position(state):
    n = len(state.get("players", []))
    offset = (state["seat_to_act"] - infer_dealer(state, max(n, 2))) % max(n, 2)
    if n == 2:
        return "BTN" if offset == 0 else "BB"
    if n == 3:
        return ("BTN", "SB", "BB")[offset]
    if n == 4:
        return ("BTN", "SB", "BB", "CO")[offset]
    if n == 5:
        return ("BTN", "SB", "BB", "HJ", "CO")[offset]
    return _POSITIONS_6MAX[offset] if offset < 6 else "CO"


def push_fold(state):
    stack = state["your_stack"]
    me = state["seat_to_act"]
    max_opp = max((p.get("stack", 0) or 0 for p in state.get("players", [])
                   if p.get("seat") != me and not p.get("is_folded")), default=stack)
    eff_bb = min(stack, max_opp) / BIG_BLIND
    if eff_bb > 12:
        return None
    hclass = hand_class(state["your_cards"])
    owed = state.get("amount_owed", 0)
    if owed > 0:
        pot_odds = owed / (state["pot"] + owed) if state["pot"] + owed > 0 else 1.0
        if hclass in _PF_TIER1:
            return {"action": "all_in"}
        if eff_bb <= 6:
            call_range = _PF_CALL_MEDIUM if pot_odds < 0.35 else _PF_CALL_TIGHT
        elif eff_bb <= 10:
            call_range = _PF_CALL_WIDE if pot_odds < 0.35 else _PF_CALL_MEDIUM
        else:
            call_range = _PF_CALL_WIDE
        return {"action": "call"} if hclass in call_range else {"action": "fold"}
    pos = position(state)
    push_range = (_PF_TIER1 if pos in ("LJ", "HJ") else _PF_TIER2 if pos == "CO"
                  else _PF_TIER3 if pos in ("BTN", "SB") else _PF_CALL_WIDE)
    if hclass in push_range:
        return {"action": "all_in"}
    return {"action": "check"} if state.get("can_check", False) else {"action": "fold"}


def to_engine_action(action_id, state):
    if action_id == FOLD:
        return {"action": "check"} if state.get("can_check") else {"action": "fold"}
    if action_id == CHECK_CALL:
        return {"action": "check"} if state.get("can_check") else {"action": "call"}
    if action_id == ALL_IN:
        return {"action": "all_in"}
    frac = 0.5 if action_id == BET_50 else 1.0
    pot = state.get("pot", 0)
    my_bet = state.get("your_bet_this_street", 0)
    to_call = state.get("amount_owed", 0)
    stack = state.get("your_stack", 0)
    raise_to = my_bet + to_call + int(round(frac * (pot + to_call)))
    max_raise = my_bet + stack
    raise_to = max(state.get("min_raise_to", 0), min(raise_to, max_raise))
    if raise_to >= max_raise:
        return {"action": "all_in"}
    if raise_to <= my_bet + to_call:
        return {"action": "call"} if to_call > 0 else {"action": "check"}
    return {"action": "raise", "amount": raise_to}


def sample(probs, rng):
    r = rng.random()
    cumulative = 0.0
    for i, p in enumerate(probs):
        cumulative += p
        if r < cumulative:
            return i
    return len(probs) - 1


def safe_default(state):
    if state.get("can_check", False):
        return {"action": "check"}
    if state.get("amount_owed", 0) > 0 and state.get("your_stack", 0) > 0:
        return {"action": "call"}
    return {"action": "fold"}


def decide(state, model, preflop, rng):
    try:
        if state.get("street", "preflop") == "preflop":
            pf = push_fold(state)
            if pf is not None:
                return pf
        features, legal = encode_state(state, preflop)
        return to_engine_action(sample(strategy(model, features, legal), rng), state)
    except Exception:
        return safe_default(state)
