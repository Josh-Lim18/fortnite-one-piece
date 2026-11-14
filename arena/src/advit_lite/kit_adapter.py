"""Translate between the AlgoSoc kit's state/action format and advitrocks9's Fullhouse format.

The kit (8-bot sit-and-gos, 2,000 chips, blinds rising from 10/20) gives every seat at the table,
including busted ones. advitrocks9 was trained on Fullhouse: only seats in the hand, a 100-chip
big blind and 10,000-chip stacks. So: keep only seats dealt into this hand, renumber them 0..n-1
in seat order, and scale chips by 100 / big_blind. Raise amounts are scaled back on the way out.
"""


def seats_in_hand(state):
    """Seats dealt into this hand: anyone not folded, or anyone who acted (folders included)."""
    acted = {h["seat"] for h in state.get("history", [])}
    return sorted(s for s in range(len(state["stacks"])) if not state["folded"][s] or s in acted)


def to_fullhouse(state):
    """Kit state -> (Fullhouse game_state, chip scale k). Fullhouse chips = kit chips * k."""
    k = 100.0 / state["big_blind"]
    seats = seats_in_hand(state)
    index = {seat: i for i, seat in enumerate(seats)}

    def scale(chips):
        return int(round(chips * k))

    players = []
    for seat in seats:
        folded = bool(state["folded"][seat])
        all_in = state["stacks"][seat] == 0 and not folded
        players.append({
            "seat": index[seat],
            "bot_id": str(seat),
            "stack": scale(state["stacks"][seat]),
            "state": "folded" if folded else "all_in" if all_in else "active",
            "is_folded": folded,
            "is_all_in": all_in,
            "bet_this_street": scale(state["bets"][seat]),
            "hole_cards": None,
        })
    log = [{"seat": index[h["seat"]], "action": h["action"], "amount": scale(h.get("amount") or 0)}
           for h in state.get("history", []) if h["seat"] in index]
    me = state["seat"]
    current = max(state["bets"])
    can_raise = "raise" in state["legal_actions"] and state.get("min_raise_to") is not None
    fullhouse = {
        "type": "action_request",
        "hand_id": str(state.get("hand_number", 0)),
        "street": state["street"],
        "seat_to_act": index[me],
        "pot": scale(state["pot"]),
        "community_cards": list(state["board"]),
        "current_bet": scale(current),
        "min_raise_to": scale(state["min_raise_to"]) if can_raise else 0,
        "amount_owed": scale(state["to_call"]),
        "can_check": state["to_call"] == 0,
        "your_cards": list(state["hole_cards"]),
        "your_stack": scale(state["stacks"][me]),
        "your_bet_this_street": scale(state["bets"][me]),
        "players": players,
        "action_log": log,
    }
    return fullhouse, k


def to_kit(action, state, k):
    """Fullhouse action -> kit action, always legal for the kit state."""
    legal = state["legal_actions"]
    kind = action.get("action")
    if kind == "all_in":
        return {"action": "all_in"}
    if kind == "raise" and "raise" in legal:
        amount = int(round(action["amount"] / k))
        return {"action": "raise", "amount": max(state["min_raise_to"], min(amount, state["max_raise_to"]))}
    if kind in ("raise", "call"):
        return {"action": "call"} if "call" in legal else {"action": "check"}
    if kind == "check":  # Fullhouse treats a check while facing a bet as a call
        return {"action": "check"} if "check" in legal else {"action": "call"}
    return {"action": "fold"} if "fold" in legal else {"action": "check"}
