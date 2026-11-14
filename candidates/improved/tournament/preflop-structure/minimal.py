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
def hook_facing_allin(agent, state, ctx):
    """HOOK: facing_allin — decide when facing an all-in (or a bet covering most of our stack)."""
    return None


# --- preflop-structure / minimal patch (helpers prefixed _pf_) -------------------------------
# Heads-up equity vs one random hand (x1000) for the 169 starting-hand classes, 6000-sample MC
# with this file's evaluator. Order: for hi rank A..2, the pair, then for each lower rank (desc)
# suited then offsuit.
_PF_EQ_STR = ("858675657662644656630642618634613622593609588596568607569586560576563569562826629616631600622579596582590549582546571539564539549534537507532510794598585602572582556575542533517536511530501513482505474508485768575550562524540523523496506474490473486461493440473446753535527523497504487483460488454469432456433454420720512485482471475445461426438420431415425388690476453458425449408428395410372409353665449427434402422382390360386337629428405416374407361372327610402377388362382343575390344371326541361331510")


def _pf_build_table():
    table = {}
    pos = 0
    for hi in range(12, -1, -1):
        for lo in range(hi, -1, -1):
            for suited in ((False,) if hi == lo else (True, False)):
                table[(hi, lo, suited)] = int(_PF_EQ_STR[pos:pos + 3]) / 1000.0
                pos += 3
    return table


_PF_EQ = _pf_build_table()


def _pf_equity(hole):
    """Heads-up equity vs a random hand for two card ints (rank = c >> 2, suit = c & 3)."""
    r1, r2 = hole[0] >> 2, hole[1] >> 2
    hi, lo = max(r1, r2), min(r1, r2)
    return _PF_EQ[(hi, lo, hi != lo and (hole[0] & 3) == (hole[1] & 3))]


# Open thresholds (HU equity) by seats from the button: 0 BTN, 1 SB, 2 BB, 3 UTG ... n-1 CO.
_PF_OPEN_LATE = 0.565   # BTN / CO   (~top 30%)
_PF_OPEN_MID = 0.590    # HJ / MP    (~top 20%)
_PF_OPEN_EARLY = 0.610  # UTG / UTG+1 (~top 14%)
_PF_OPEN_SB = 0.575
_PF_VALUE_3BET = 0.655  # non-pairs: AKs, AKo, AQs, AJs by this table


def _pf_raise(state, total):
    if "raise" not in (S(state, "legal_actions", []) or []):
        return None
    return {"action": "raise", "amount": int(total)}


def _pf_call_or_check(state):
    legal = S(state, "legal_actions", []) or []
    return {"action": "call"} if "call" in legal else {"action": "check"}


def _pf_fold_or_check(state):
    legal = S(state, "legal_actions", []) or []
    return {"action": "check"} if "check" in legal else {"action": "fold"}


def hook_preflop(agent, state, ctx):
    """HOOK: preflop — preflop decisions other than facing all-in.
    Minimal patch: replace the 32-sample win rate vs ALL opponents with a heads-up equity table,
    position-based open thresholds, a fixed open / iso size, and simple call / 3-bet rules."""
    bets = S(state, "bets")
    stacks = S(state, "stacks")
    bb = S(state, "big_blind", 20) or 20
    to_call = S(state, "to_call", 0) or 0
    me = state.get("seat", getattr(agent, "seat", 0))
    if not bets or not stacks or me is None or me >= len(bets):
        return None  # cannot read the table structure: defer to the incumbent
    my_stack = stacks[me]
    if to_call > 0 and to_call >= 0.5 * my_stack:
        return None  # facing (near) all-in belongs to hook_facing_allin / incumbent
    n = len(bets)
    button = S(state, "button")
    pos = (me - button) % n if button is not None else 4
    hole = ctx["hole"]
    e = _pf_equity(hole)
    pair = (hole[0] >> 2) == (hole[1] >> 2)
    cur = max(bets)
    folded = state.get("folded") or [False] * n
    my_bet = bets[me]
    eff = my_stack + my_bet  # chips I can put in this hand (street total)

    if cur <= bb:
        # Unopened or limped pot.
        bb_seat = (button + 2) % n if button is not None else None
        limpers = sum(1 for i in range(n) if i != me and i != bb_seat and not folded[i] and bets[i] >= bb)
        if pos == 0 or pos >= n - 1:
            thr = _PF_OPEN_LATE
        elif pos == 1:
            thr = _PF_OPEN_SB
        elif pos == 2:
            thr = _PF_OPEN_SB  # BB: raise for value / iso
        elif pos >= n - 3:
            thr = _PF_OPEN_MID
        else:
            thr = _PF_OPEN_EARLY
        thr += 0.01 * limpers  # isolate a bit tighter behind limpers (they call raises)
        if e >= thr:
            size = 3 * bb + bb * limpers + (bb if pos in (1, 2) else 0)
            act = _pf_raise(state, min(size, eff))
            if act is not None:
                return act
            return _pf_call_or_check(state)
        if to_call == 0:
            return {"action": "check"}
        # Cheap entry: over-limp / complete with pairs and decent hands when others limped.
        if limpers >= 1 and (pair or e >= 0.54) and to_call <= bb:
            return _pf_call_or_check(state)
        if pos == 1 and e >= 0.52 and to_call <= bb // 2 + 1:
            return _pf_call_or_check(state)
        return _pf_fold_or_check(state)

    # Facing a raise (not near all-in).
    raises = 0
    for ev in (S(state, "history") or []):
        if isinstance(ev, dict) and ev.get("action") == "raise" and ev.get("street", "preflop") == "preflop":
            raises += 1
    raises = max(raises, 1)
    callers = max(0, sum(1 for i in range(n) if i != me and not folded[i] and bets[i] >= cur) - 1)
    if raises == 1:
        if (e >= _PF_VALUE_3BET and not pair) or (pair and hole[0] >> 2 >= 6):  # AQs+, AKo; 88+
            size = 3 * cur + cur * callers
            if size >= 0.4 * eff:  # do not leave an awkward stack behind: shove instead
                size = eff
            act = _pf_raise(state, min(size, eff))
            return act if act is not None else _pf_call_or_check(state)
        price = to_call / float(bb)
        if price <= 1.01 and e >= 0.45:  # e.g. BB vs a min-raise
            return _pf_call_or_check(state)
        call_thr = 0.585 if price <= 3 else (0.61 if price <= 6 else 0.635)
        if e >= call_thr and to_call <= 0.12 * eff:
            return _pf_call_or_check(state)
        if pair and to_call <= 0.06 * eff:  # set-mine cheaply
            return _pf_call_or_check(state)
        return _pf_fold_or_check(state)
    # Facing a 3-bet or more.
    if (pair and hole[0] >> 2 >= 10) or (not pair and e >= 0.67):  # QQ+, AKs: get it in
        act = _pf_raise(state, state.get("max_raise_to") or eff)
        return act if act is not None else _pf_call_or_check(state)
    if ((pair and hole[0] >> 2 >= 8) or (not pair and e >= 0.655)) and to_call <= 0.25 * eff:  # TT-JJ, AKo, AQs: call
        return _pf_call_or_check(state)
    return _pf_fold_or_check(state)


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
