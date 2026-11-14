"""dev.fun Textured policy port: B public-candidate intake, not C tuning.

Source: devfun-org/poker-arena-starter-kit/assets/decide_textured.py
Revision: fc19bb25e9c6e8fabc26099d6a767241fc99fc2f
The ranges, texture classifier, fractions and coarse postflop policy are retained.
Adapter changes: legal Imperial raise-to bounds, button-relative positions with
extra early seats using UTG, unraised blind-facing opens, no two-second gate.
No performance claim; important inherited limitations are in textured_notes.md.

MIT License

Copyright (c) 2026 dev.fun

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import Optional

FALLBACK_REASONING = '{vr: "std", ke: "legal", pp: "pot control"}'

# Reuse OPENING_RANGES + SEAT_TO_POS + _hand_class from decide_ranged.py
# in a real edit; inlined here for self-containment.
OPENING_RANGES = {
    "UTG": {"AA","KK","QQ","JJ","TT","99","AKs","AKo","AQs"},
    "MP":  {"AA","KK","QQ","JJ","TT","99","88","AKs","AKo","AQs","AQo","AJs","KQs"},
    "CO":  {"AA","KK","QQ","JJ","TT","99","88","77","66","55",
            "AKs","AKo","AQs","AQo","AJs","AJo","ATs","KQs","KQo","KJs","KTs",
            "QJs","QTs","JTs","T9s","98s"},
    "BTN": {"AA","KK","QQ","JJ","TT","99","88","77","66","55","44","33","22",
            "AKs","AKo","AQs","AQo","AJs","AJo","ATs","ATo",
            "A9s","A8s","A7s","A6s","A5s","A4s","A3s","A2s",
            "KQs","KQo","KJs","KJo","KTs","K9s",
            "QJs","QTs","Q9s","JTs","J9s","T9s","98s","87s","76s"},
    "SB":  {"AA","KK","QQ","JJ","TT","99","88","AKs","AKo","AQs","AQo","AJs","ATs","KQs","KJs","QJs"},
    "BB":  {"AA","KK","QQ","JJ","TT","AKs","AKo","AQs"},
}
SEAT_TO_POS = {1: "BTN", 2: "SB", 3: "BB", 4: "UTG", 5: "MP", 6: "CO"}

# Bet sizing per board texture (fraction of pot).
SIZING = {
    "dry":      {"flop": 0.33, "turn": 0.50, "river": 0.66},
    "wet":      {"flop": 0.66, "turn": 0.75, "river": 0.75},
    "neutral":  {"flop": 0.50, "turn": 0.60, "river": 0.66},
}


def _hand_class(hole):
    if len(hole) != 2: return ""
    ranks = "23456789TJQKA"
    r1, s1 = hole[0][0].upper(), hole[0][-1].lower()
    r2, s2 = hole[1][0].upper(), hole[1][-1].lower()
    if r1 not in ranks or r2 not in ranks: return ""
    if ranks.index(r1) < ranks.index(r2):
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2: return r1 + r2
    return f"{r1}{r2}{'s' if s1 == s2 else 'o'}"


def _board_texture(board: list[str]) -> str:
    """Classify board as dry / wet / neutral based on suits + connectedness."""
    if len(board) < 3:
        return "neutral"
    suits = [c[-1].lower() for c in board]
    ranks = sorted("23456789TJQKA".index(c[0].upper()) for c in board
                   if c[0].upper() in "23456789TJQKA")
    monotone = len(set(suits)) == 1
    two_tone = len(set(suits)) == 2 and max(suits.count(s) for s in set(suits)) >= 2
    connected = (max(ranks) - min(ranks)) <= 4 if ranks else False
    paired = len(set(c[0] for c in board)) < len(board)
    if monotone or (two_tone and connected):
        return "wet"
    if paired and not connected:
        return "dry"
    if connected:
        return "wet"
    return "dry"


def _street(boardCards: list[str]) -> str:
    return ("flop", "turn", "river")[max(0, min(len(boardCards) - 3, 2))] \
        if boardCards else "preflop"


def decide(table: dict, deadline_s: float = 10.0,
           research_context: Optional[dict] = None) -> dict:
    allowed = table.get("allowedActions") or {}
    available = allowed.get("availableActions") or []

    # Imperial permits 10ms; this fixed-cost policy needs no two-second gate.

    self_seat_num = table.get("selfSeatNumber") or 0
    seats = table.get("seats") or []
    self_seat = next((s for s in seats if s.get("seatNumber") == self_seat_num), {})
    hole = list(self_seat.get("holeCards") or [])
    board = list(table.get("boardCards") or [])
    street = _street(board)
    pos = SEAT_TO_POS.get(self_seat_num, "MP")
    cls = _hand_class(hole)
    pot = int(table.get("potChips") or 0)
    call_chips = int(allowed.get("callChips") or 0)

    # Preflop — same as ranged.
    if street == "preflop" and (call_chips == 0 or table.get("_unraised_preflop", False)) and cls in OPENING_RANGES.get(pos, set()):
        rr = allowed.get("raiseRange") or {}
        lo = int(rr.get("min") or 4)
        hi = int(rr.get("max") or lo)
        amt = max(lo, min(lo * 2, hi))
        action = "raise" if "raise" in available else ("bet" if "bet" in available else "check")
        if action in ("raise", "bet"):
            return {"action": action, "amount": amt,
                    "message": f"open {cls} from {pos}",
                    "reasoning": f'{{vr: "std", ke: "{cls} open", pp: "IP barrel T", sr: "2.5bb open"}}'}

    if street == "preflop":
        if call_chips > 0 and cls not in (OPENING_RANGES.get("BB", set()) | {"99","88","KQs","QJs","JTs"}):
            return {"action": "fold", "message": f"{cls} not in defend",
                    "reasoning": FALLBACK_REASONING}
        if call_chips > 0 and "call" in available:
            return {"action": "call", "message": f"defend {cls}",
                    "reasoning": FALLBACK_REASONING}
        if "check" in available:
            return {"action": "check", "message": "free preflop",
                    "reasoning": FALLBACK_REASONING}
        return {"action": "fold", "message": "no preflop play",
                "reasoning": FALLBACK_REASONING}

    # Postflop with texture-aware sizing.
    texture = _board_texture(board)
    pair_with_board = bool({c[0].upper() for c in hole} & {c[0].upper() for c in board})

    if call_chips == 0:
        if pair_with_board and ("bet" in available or "raise" in available):
            size = SIZING[texture][street]
            br = allowed.get("betRange") or allowed.get("raiseRange") or {}
            lo = int(br.get("min") or 1)
            hi = int(br.get("max") or lo)
            amt = max(lo, min(int(pot * size), hi))
            act = "bet" if "bet" in available else "raise"
            return {"action": act, "amount": amt,
                    "message": f"{texture} {street} cbet {int(size*100)}%",
                    "reasoning": f'{{vr: "std", ke: "{cls} pair", bf: [{texture}], pp: "IP barrel T", sr: "{int(size*100)}% pot"}}'}
        return {"action": "check" if "check" in available else "fold",
                "message": f"check {street} on {texture}", "reasoning": FALLBACK_REASONING}

    pot_odds = call_chips / max(pot + call_chips, 1)
    if pair_with_board and pot_odds < 0.4 and "call" in available:
        return {"action": "call", "message": f"call pair on {texture}",
                "reasoning": f'{{vr: "ln:bet", ke: "pot odds {int(pot_odds*100)}%", bf: [{texture}], pp: "showdown"}}'}
    return {"action": "fold", "message": f"fold to bet on {texture}",
            "reasoning": FALLBACK_REASONING}


# ---------------------------------------------------------------------------
# Imperial interface. The upstream policy uses canonical six-seat numbers;
# actual player indexes are mapped from the real button at every decision.
# ---------------------------------------------------------------------------

_POS_TO_CANONICAL = {position: seat for seat, position in SEAT_TO_POS.items()}


def _position(seat, button, count):
    """Keep the source's six ranges; additional early seats use its UTG range."""
    distance = (seat - button) % count
    if count == 2:
        return "SB" if distance == 0 else "BB"
    if distance == 0:
        return "BTN"
    if distance == 1:
        return "SB"
    if distance == 2:
        return "BB"
    if distance == count - 1:
        return "CO"
    if distance == count - 2:
        return "MP"
    return "UTG"


def _unraised_preflop(state):
    if state["street"] != "preflop" or state["board"]:
        return False
    # Check both the observed bet level and history, so missing blind entries
    # cannot be mistaken for a voluntary raise (nor a high live bet for blinds).
    if max(state["bets"], default=0) > state["big_blind"]:
        return False
    return not any(event.get("action") in ("raise", "all_in")
                   for event in state.get("history", []))


def _adapt_state(state):
    position = _position(state["seat"], state["button"], len(state["stacks"]))
    canonical = _POS_TO_CANONICAL[position]
    legal = list(state["legal_actions"])
    lower, upper = state.get("min_raise_to"), state.get("max_raise_to")
    if "raise" in legal and lower is not None and upper is not None:
        bounds = {"min": lower, "max": upper}
    else:
        bounds = {}
    return {
        "selfSeatNumber": canonical,
        "seats": [{"seatNumber": canonical, "holeCards": list(state["hole_cards"])}],
        "boardCards": list(state["board"]),
        "potChips": state["pot"],
        "_unraised_preflop": _unraised_preflop(state),
        "allowedActions": {
            "availableActions": legal,
            "canCheck": "check" in legal,
            "callChips": state["to_call"],
            "raiseRange": bounds,
            # Both protocols use total committed this street, not an increment.
            "amountSemantics": "toAmount",
        },
    }


class Agent:
    """Stateless, deterministic source-policy adapter."""
    def act(self, state):
        legal = state.get("legal_actions", [])
        fallback = {"action": "check" if "check" in legal else "fold"}
        try:
            raw = decide(_adapt_state(state), deadline_s=0.010)
            action = raw.get("action")
            if action in ("raise", "bet"):
                lower, upper = state.get("min_raise_to"), state.get("max_raise_to")
                if "raise" in legal and lower is not None and upper is not None:
                    return {"action": "raise", "amount": int(min(upper, max(lower, raw["amount"])))}
                return {"action": "call"} if "call" in legal else fallback
            if action in legal:
                return {"action": action}
            return fallback
        except (KeyError, TypeError, ValueError, IndexError):
            return fallback
