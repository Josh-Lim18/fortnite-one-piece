"""v0 skeleton: the incumbent (VIVelev Monte Carlo, candidates/incumbent/bot.py) refactored into hooks.

Behaviour is intended to match the incumbent exactly except for the safety layer:
  * every returned action passes `sanitize()` (legal action, int raise-to clamped to [min, max]);
  * every exception falls back to check/fold.
Tournament solvers change ONLY the hook(s) they are assigned (search for `HOOK:`), so that winners merge cleanly.

Official API (inferred from the incumbent): Agent() with no args, optional on_table_start(info), act(state).
Known state keys: hole_cards, board, legal_actions, min_raise_to, max_raise_to, folded, seat.
Other keys (pot, to_call, stacks, bets, button, street, big_blind, history) are read through S() with fallbacks,
because the official names are not confirmed yet. Keep all key access going through S().
"""
import random
import time

MAX_SAMPLES = 32
THINK_SECONDS = 0.0012
RANKS = "23456789TJQKA"
SUITS = "shdc"


# ---------------------------------------------------------------------------
# State access (single place to adapt key names once the official format is confirmed)
# ---------------------------------------------------------------------------
_ALIASES = {
    "hole_cards": ("hole_cards", "hole"),
    "legal_actions": ("legal_actions", "legal"),
    "pot": ("pot", "pot_size"),
    "to_call": ("to_call", "amount_to_call", "call_amount"),
    "stacks": ("stacks", "stack_sizes"),
    "bets": ("bets", "street_bets", "committed"),
    "button": ("button", "dealer", "button_seat"),
    "street": ("street", "round"),
    "big_blind": ("big_blind", "bb"),
    "history": ("history", "action_history", "actions"),
}


def S(state, key, default=None):
    for k in _ALIASES.get(key, (key,)):
        if k in state and state[k] is not None:
            return state[k]
    return default


def _card(text):
    return RANKS.index(text[0].upper()) * 4 + SUITS.index(text[1].lower())


def _straight(mask):
    consecutive = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if consecutive:
        return consecutive.bit_length() + 3
    return 3 if mask & 0x100F == 0x100F else -1


def _kickers(mask, count):
    result = 0
    shift = 16
    for _ in range(count):
        rank = mask.bit_length() - 1
        result |= rank << shift
        mask ^= 1 << rank
        shift -= 4
    return result


def _evaluate(cards):
    """Best-five evaluator for 5-7 distinct cards; higher wins."""
    ranks = pairs = trips = quads = 0
    suits = [0, 0, 0, 0]
    for card in cards:
        bit = 1 << (card >> 2)
        quads |= trips & bit
        trips |= pairs & bit
        pairs |= ranks & bit
        ranks |= bit
        suits[card & 3] |= bit
    flush = 0
    for suited in suits:
        if suited.bit_count() >= 5:
            straight = _straight(suited)
            if straight >= 0:
                return (8 << 20) | (straight << 16)
            flush = suited
            break
    if quads:
        rank = quads.bit_length() - 1
        return (7 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 1) >> 4)
    if trips:
        rank = trips.bit_length() - 1
        other_pairs = pairs & ~(1 << rank)
        if other_pairs:
            return (6 << 20) | (rank << 16) | ((other_pairs.bit_length() - 1) << 12)
    if flush:
        return (5 << 20) | _kickers(flush, 5)
    straight = _straight(ranks)
    if straight >= 0:
        return (4 << 20) | (straight << 16)
    if trips:
        return (3 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 2) >> 4)
    if pairs:
        high = pairs.bit_length() - 1
        rest = pairs ^ (1 << high)
        if rest:
            low = rest.bit_length() - 1
            remaining = ranks & ~(1 << high) & ~(1 << low)
            return (2 << 20) | (high << 16) | (low << 12) | (_kickers(remaining, 1) >> 8)
        return (1 << 20) | (high << 16) | (_kickers(ranks ^ (1 << high), 3) >> 4)
    return _kickers(ranks, 5)


def _remaining_opponents(state):
    return sum(not folded for seat, folded in enumerate(state["folded"]) if seat != state["seat"])


def _estimate_win_rate(hole, board, opponents, rng, deadline=None, max_samples=MAX_SAMPLES):
    """Incumbent statistic: uniform rollouts vs random hands; ties count as wins."""
    if opponents == 0:
        return 1.0, 0
    known = set(hole + board)
    deck = [card for card in range(52) if card not in known]
    missing = 5 - len(board)
    wins = samples = 0
    for _ in range(max_samples):
        if samples and deadline is not None and time.perf_counter() >= deadline:
            break
        draw = rng.sample(deck, missing + 2 * opponents)
        complete = board + draw[:missing]
        score = _evaluate(hole + complete)
        won = True
        for offset in range(missing, len(draw), 2):
            if _evaluate(draw[offset:offset + 2] + complete) > score:
                won = False
                break
        wins += won
        samples += 1
    return wins / samples, samples


# ---------------------------------------------------------------------------
# Safety layer (mandatory for every candidate)
# ---------------------------------------------------------------------------
def safe_default(state):
    legal = S(state, "legal_actions", []) or []
    return {"action": "check"} if "check" in legal else {"action": "fold"}


def sanitize(action, state):
    legal = S(state, "legal_actions", []) or []
    if not isinstance(action, dict) or action.get("action") not in legal:
        # map common mistakes to the closest legal action
        a = action.get("action") if isinstance(action, dict) else None
        if a == "check" and "call" in legal:
            return {"action": "fold"} if "fold" in legal else {"action": "call"}
        if a == "call" and "check" in legal:
            return {"action": "check"}
        if a == "raise" and "call" in legal:
            return {"action": "call"}
        if a == "raise" and "check" in legal:
            return {"action": "check"}
        return safe_default(state)
    if action["action"] == "raise":
        lo, hi = state.get("min_raise_to"), state.get("max_raise_to")
        try:
            amt = int(round(float(action.get("amount", lo))))
        except (TypeError, ValueError):
            amt = lo
        if lo is None or hi is None:
            return safe_default(state)
        return {"action": "raise", "amount": int(max(lo, min(hi, amt)))}
    return {"action": action["action"]}


# ---------------------------------------------------------------------------
# Opponent stats tracker (shared, minimal; HOOK: opponent_model may replace/extend)
# ---------------------------------------------------------------------------
class OpponentStats:
    """Counts per seat from observed public events. Robust to missing/odd events."""

    def __init__(self):
        self.seats = {}
        self._hand = None
        self._street = None
        self._vpip_done = set()
        self._facing_bet = False

    def _s(self, seat):
        return self.seats.setdefault(seat, {"hands": 0, "vpip": 0, "pfr": 0, "shove_pf": 0,
                                            "fold_vs_bet": 0, "faced_bet": 0, "bets_raises": 0,
                                            "calls": 0, "showdowns": []})

    def observe(self, ev):
        try:
            t = ev.get("type")
            if t == "hand_start":
                self._hand = ev.get("hand_id")
                self._vpip_done = set()
                self._street = "preflop"
                self._facing_bet = False
                for s in range(len(ev.get("stacks", []))):
                    self._s(s)["hands"] += 1
            elif t == "board":
                self._street = ev.get("street")
                self._facing_bet = False
            elif t == "action":
                seat, a = ev.get("seat"), ev.get("action")
                st = self._s(seat)
                street = ev.get("street", self._street)
                if a == "post":
                    return
                if self._facing_bet and a in ("fold", "call", "raise"):
                    st["faced_bet"] += 1
                    st["fold_vs_bet"] += a == "fold"
                if a in ("call", "raise") and street == "preflop" and seat not in self._vpip_done:
                    st["vpip"] += 1
                    self._vpip_done.add(seat)
                if a == "raise":
                    st["bets_raises"] += 1
                    self._facing_bet = True
                    if street == "preflop":
                        st["pfr"] += 1
                        if (ev.get("amount") or 0) >= 1900:
                            st["shove_pf"] += 1
                elif a == "call":
                    st["calls"] += 1
            elif t == "showdown":
                for seat, cards in (ev.get("hands") or {}).items():
                    self._s(int(seat))["showdowns"].append(list(cards))
                    self._s(int(seat))["showdowns"] = self._s(int(seat))["showdowns"][-50:]
        except Exception:
            pass

    def rate(self, seat, num, den, prior=0.0, k=10):
        st = self.seats.get(seat)
        if not st:
            return prior
        return (st[num] + prior * k) / (st[den] + k)


# ---------------------------------------------------------------------------
# HOOKS — default implementations reproduce the incumbent. Return None to defer to the incumbent policy.
# ---------------------------------------------------------------------------
# --- shove-defense (minimal patch): stateless preflop jam-calling rule. Postflop defers to the incumbent. ---
# Equity (x1000, ties split) of each starting-hand class vs ONE uniformly random hand (offline MC, 6000 deals each).
_SD_EQ1 = {
    "AA": 862, "KK": 829, "QQ": 793, "JJ": 776, "TT": 756, "99": 722, "88": 694, "AKs": 679, "77": 671, "AJs": 671,
    "AQs": 661, "AKo": 652, "AQo": 645, "ATs": 641, "66": 638, "KQs": 636, "A9s": 634, "AJo": 631, "KTs": 625,
    "ATo": 622, "KQo": 622, "KJs": 620, "A8s": 614, "A7s": 608, "A8o": 607, "KJo": 605, "K9s": 605, "A9o": 604,
    "55": 602, "A6s": 601, "A5s": 600, "QTs": 599, "QJs": 595, "KTo": 594, "A3s": 594, "A4s": 590, "A7o": 587,
    "K8s": 586, "A6o": 585, "QJo": 585, "JTs": 582, "A5o": 575, "QTo": 575, "K9o": 574, "A2s": 574, "Q9s": 573,
    "K7s": 570, "A4o": 564, "Q8s": 564, "44": 561, "JTo": 561, "A3o": 560, "K8o": 555, "Q9o": 554, "K7o": 553,
    "K6s": 553, "K5s": 552, "A2o": 551, "J9s": 548, "J8s": 547, "K4s": 546, "K6o": 545, "Q8o": 545, "K3s": 541,
    "33": 540, "K2s": 539, "J9o": 538, "Q7s": 538, "T9s": 536, "T8s": 526, "K5o": 524, "J7s": 524, "Q4s": 524,
    "Q6s": 522, "J8o": 520, "K4o": 519, "K3o": 516, "Q6o": 516, "98s": 516, "Q7o": 515, "Q5s": 514, "K2o": 509,
    "T9o": 508, "22": 506, "Q3s": 506, "Q2s": 505, "T7s": 500, "J7o": 499, "Q5o": 498, "J4s": 498, "J6s": 498,
    "J5s": 493, "97s": 492, "Q4o": 491, "Q3o": 488, "J3s": 486, "T6s": 485, "98o": 484, "T8o": 484, "87s": 480,
    "J2s": 480, "T7o": 478, "96s": 478, "T5s": 472, "T4s": 469, "Q2o": 466, "J6o": 466, "86s": 466, "J5o": 462,
    "97o": 461, "T6o": 459, "87o": 453, "T3s": 453, "J3o": 452, "95s": 451, "J4o": 450, "T2s": 450, "T5o": 448,
    "75s": 448, "76s": 448, "85s": 447, "J2o": 439, "T3o": 437, "76o": 437, "96o": 437, "93s": 436, "95o": 430,
    "86o": 430, "94s": 428, "84s": 427, "65s": 425, "T4o": 423, "54s": 421, "74s": 421, "T2o": 415, "64s": 411,
    "92s": 409, "85o": 408, "82s": 408, "94o": 407, "75o": 406, "83s": 406, "73s": 404, "92o": 401, "93o": 399,
    "63s": 397, "53s": 396, "65o": 393, "84o": 387, "74o": 386, "72s": 386, "43s": 384, "54o": 384, "64o": 384,
    "42s": 382, "62s": 380, "83o": 378, "73o": 374, "82o": 371, "32s": 370, "52s": 368, "53o": 361, "63o": 357,
    "52o": 354, "43o": 347, "72o": 346, "62o": 344, "42o": 332, "32o": 326
}

_SD_RANKS = "23456789TJQKA"
# Hands that still call once someone else is already in the jam pot (3-way: need ~34% vs random + caller range).
_SD_ONE_CALLER = {"AA", "KK", "QQ", "JJ", "TT", "99", "AKs", "AKo", "AQs", "AQo", "AJs"}
# Two or more already in (4-way+: need ~25% vs random + two calling ranges).
_SD_MULTI_CALLER = {"AA", "KK", "QQ", "JJ", "TT", "AKs", "AKo"}
_SD_PREMIUM = {"AA", "KK", "QQ", "AKs"}


def _sd_key(hole):
    """169-class key ('AKs', 'T9o', '77') from the skeleton's int cards (rank*4 + suit)."""
    a, b = hole[0], hole[1]
    ra, rb = a >> 2, b >> 2
    if ra < rb:
        ra, rb = rb, ra
    if ra == rb:
        return _SD_RANKS[ra] * 2
    return _SD_RANKS[ra] + _SD_RANKS[rb] + ("s" if (a & 3) == (b & 3) else "o")


def hook_facing_allin(agent, state, ctx):
    """HOOK: facing_allin — decide when facing an all-in (or a bet covering most of our stack).

    Minimal patch (preflop only; postflop returns None -> incumbent):
      * nobody has called the jam yet: call with equity-vs-random >= 0.515, +0.006 per player still to act,
        +0.03 per still-to-act player who had voluntarily raised before the jam (their range is strong);
      * exactly one other player already in: _SD_ONE_CALLER only;
      * two or more already in: _SD_MULTI_CALLER only.
    Hypothesis: jams at these tables mostly come from shovers with ~random ranges; callers are not random.
    """
    if ctx.get("board"):
        return None
    bets = S(state, "bets")
    folded = state.get("folded")
    if not bets or folded is None or len(bets) != len(folded):
        return None
    me = state.get("seat", agent.seat)
    bb = S(state, "big_blind", 20) or 20
    legal = S(state, "legal_actions", []) or []
    top = max(bets)
    in_pot = pending = openers = 0
    for i, b in enumerate(bets):
        if i == me or folded[i]:
            continue
        if b >= 0.9 * top:
            in_pot += 1
        else:
            pending += 1
            openers += b > bb
    key = _sd_key(ctx["hole"])
    callers = max(0, in_pot - 1)
    if callers == 0:
        call = _SD_EQ1.get(key, 0) >= 515 + 6 * pending + 30 * openers
    elif callers == 1:
        call = key in _SD_ONE_CALLER
    else:
        call = key in _SD_MULTI_CALLER
    if not call:
        return {"action": "check"} if "check" in legal else {"action": "fold"}
    if key in _SD_PREMIUM and "raise" in legal and pending:
        return {"action": "raise", "amount": state.get("max_raise_to")}
    return {"action": "call"} if "call" in legal else {"action": "check"}


def hook_preflop(agent, state, ctx):
    """HOOK: preflop — preflop decisions other than facing all-in."""
    return None


def hook_betting(agent, state, ctx):
    """HOOK: betting — postflop when nothing to call (to_call == 0): check, value bet or bluff.
    Use agent.size(state, ctx, intent, default_frac) for amounts."""
    return None


def hook_facing_bet(agent, state, ctx):
    """HOOK: facing_bet — postflop when facing a bet/raise that is NOT (near) all-in: fold/call/raise."""
    return None


def hook_sizing(agent, state, ctx, intent):
    """HOOK: sizing — given intent in {'value','thin_value','bluff','probe','raise_value','raise_bluff'},
    return a raise-to total (int) or None to use the default pot fraction."""
    return None


def pot_raise_to(state, frac):
    """Raise-to total for a bet/raise of `frac` x pot (pot measured after calling). Falls back to min raise."""
    bets = S(state, "bets")
    pot = S(state, "pot")
    to_call = S(state, "to_call", 0) or 0
    lo = state.get("min_raise_to")
    if bets is None or pot is None:
        return lo
    return int(max(bets) + frac * (pot + to_call))


# Extra per-solver trackers: append a class with observe(event) (and anything else) in YOUR section;
# the Agent instantiates each one and feeds it every event: self.trackers[cls.__name__].
EXTRA_TRACKERS = []


def incumbent_policy(win_rate, state):
    legal = S(state, "legal_actions", [])
    if win_rate > 0.75 and "raise" in legal:
        bound = "max_raise_to" if win_rate > 0.85 else "min_raise_to"
        return {"action": "raise", "amount": int(state[bound])}
    if win_rate > 0.5 and "call" in legal:
        return {"action": "call"}
    if "check" in legal:
        return {"action": "check"}
    return {"action": "fold"}


class Agent:
    def __init__(self, *args, **kwargs):
        self.on_table_start({})

    def on_table_start(self, info):
        info = info or {}
        self.seat = int(info.get("seat", 0) or 0)
        self.rng = random.Random(2018 + self.seat)
        self.last_samples = 0
        self.stats = OpponentStats()
        self.trackers = {}
        for cls in EXTRA_TRACKERS:
            try:
                self.trackers[cls.__name__] = cls()
            except Exception:
                pass
        self.info = dict(info)

    def size(self, state, ctx, intent, default_frac):
        amt = hook_sizing(self, state, ctx, intent)
        return int(amt) if amt is not None else pot_raise_to(state, default_frac)

    def observe(self, event):
        self._observe_seen = True
        self._feed(event)

    def _feed(self, event):
        self.stats.observe(event)
        for t in self.trackers.values():
            try:
                t.observe(event)
            except Exception:
                pass

    # --- kit event layer (AlgoSoc kit calls act() and on_hand_end(); never observe()) ---------------
    def _kit_new_hand(self, hid, n_seats):
        self._hist_hand, self._hist_n, self._hist_k, self._hist_street = hid, 0, 0, "preflop"
        self._feed({"type": "hand_start", "hand_id": hid, "stacks": [0] * n_seats})

    def _kit_replay(self, events, board):
        streets = ("preflop", "flop", "turn", "river")
        for ev in events:
            if not isinstance(ev, dict):
                continue
            st = ev.get("street", self._hist_street)
            if st != self._hist_street and st in streets:
                k = {"flop": 3, "turn": 4, "river": 5}.get(st, 0)
                self._feed({"type": "board", "hand_id": self._hist_hand, "street": st, "board": list(board[:k])})
                self._hist_street = st
            a = ev.get("action")
            if a in ("small_blind", "big_blind"):
                self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": "preflop",
                            "action": "post", "amount": ev.get("amount", 0)})
                continue
            self._hist_k += 1
            self._feed({"type": "action", "hand_id": self._hist_hand, "seat": ev.get("seat"), "street": st,
                        "action": a, "amount": ev.get("amount", 0)})

    def _ingest_history(self, state):
        """Replay new events from state history (kit format) into the trackers."""
        if getattr(self, "_observe_seen", False):
            return
        hist = S(state, "history") or []
        hid = state.get("hand_number", state.get("hand_id"))
        if hid != getattr(self, "_hist_hand", object()):
            self._kit_new_hand(hid, len(state.get("folded") or S(state, "stacks") or []))
        self._kit_replay(hist[self._hist_n:], state.get("board") or [])
        self._hist_n = len(hist)

    def on_hand_end(self, summary):
        try:
            if getattr(self, "_observe_seen", False) or not isinstance(summary, dict):
                return
            hid = summary.get("hand_number")
            stacks = summary.get("stacks") or []
            if hid != getattr(self, "_hist_hand", object()):
                self._kit_new_hand(hid, len(stacks))
            hist = [h for h in (summary.get("history") or []) if h.get("action") not in ("small_blind", "big_blind")]
            self._kit_replay(hist[self._hist_k:], summary.get("board") or [])
            shown = summary.get("shown") or {}
            if shown:
                self._feed({"type": "showdown", "hand_id": hid,
                            "hands": {int(s): list(c) for s, c in shown.items() if c},
                            "winners": {int(w.get("seat")): w.get("amount", 0) for w in (summary.get("winners") or [])}})
            start = int(self.info.get("starting_stack", 0) or 0)
            self._feed({"type": "hand_end", "hand_id": hid,
                        "deltas": [int(x) - start for x in stacks] if start else []})
            self._hist_hand = ("ended", hid)
        except Exception:
            pass

    def act(self, state):
        try:
            self._ingest_history(state)
        except Exception:
            pass
        try:
            return sanitize(self._act(state), state)
        except Exception:
            return safe_default(state)

    def _act(self, state):
        started = time.perf_counter()
        hole = [_card(c) for c in S(state, "hole_cards")]
        board = [_card(c) for c in state.get("board", [])]
        opps = _remaining_opponents(state)
        ctx = {"hole": hole, "board": board, "opponents": opps, "started": started}
        stacks = S(state, "stacks")
        to_call = S(state, "to_call", 0) or 0
        me = state.get("seat", self.seat)
        my_stack = stacks[me] if stacks else None
        facing_allin = my_stack is not None and to_call > 0 and to_call >= 0.5 * my_stack
        if facing_allin:
            act = hook_facing_allin(self, state, ctx)
            if act is not None:
                return act
        street = S(state, "street") or ("preflop" if not board else "postflop")
        if street == "preflop":
            act = hook_preflop(self, state, ctx)
        elif to_call == 0:
            act = hook_betting(self, state, ctx)
        else:
            act = hook_facing_bet(self, state, ctx)
        if act is not None:
            return act
        win_rate, self.last_samples = _estimate_win_rate(hole, board, opps, self.rng,
                                                         deadline=started + THINK_SECONDS)
        ctx["win_rate"] = win_rate
        act = incumbent_policy(win_rate, state)
        if act.get("action") == "raise":
            intent = "value" if win_rate > 0.85 else "thin_value"
            amt = hook_sizing(self, state, ctx, intent)
            if amt is not None:
                act = {"action": "raise", "amount": int(amt)}
        return act
