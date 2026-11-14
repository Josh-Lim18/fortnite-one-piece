

# ===========================================================================================
# autopicker-lc LAYERS 2-4: opponent profiles -> personalities -> auto picker (4 states) -> safety nets
# Layer 1 (baseline) = tournament plug-ins (_cand_*) + the baseline rules in the hooks below.
# Every exploit is a hypothesis; the picker only leans on it in proportion to evidence.
# ===========================================================================================
import collections as _v1_col
import math as _v1_math

_V1_STATS = ("vpip", "pfr", "shove", "aggr", "fold_vs_bet")
_V1_PRIOR = {"vpip": 0.30, "pfr": 0.15, "shove": 0.02, "aggr": 0.35, "fold_vs_bet": 0.45}
_V1_PRIOR_K = 12.0          # prior strength (pseudo-observations)
_V1_RECENT = 30             # recent window per stat
_V1_DECAY = 0.997           # long-run decay per observation (forgets slowly)
_V1_Z_ENTER = 3.0           # surprise needed to enter DEVIATING
_V1_Z_EXIT = 1.5            # surprise below which DEVIATING relaxes back
_V1_CHANGE_HANDS = 40       # DEVIATING this long (seat-hands) => CHANGED (relearn)
_V1_CONF_K = 30.0           # confidence = hands / (hands + K)
_V1_STOP_HANDS = 40         # stop-loss window (attributed hands)
_V1_STOP_BB = -150.0        # stop-loss threshold over the window, in big blinds
_V1_STOP_COOLDOWN = 60      # hands with exploits off after the stop-loss fires
_V1_MC_SECONDS = 0.0003     # equity sampling budget per decision (review #12: match v1-fast thinking time)

_V1_USE_EXPLOIT = True      # False => layer 1 baseline only (ablation)
_V1_USE_PICKER = True       # False => personalities only, no deviation states / stop-loss (ablation)

IN_CHARACTER, DEVIATING, CHANGED, REACTIVE = "in_character", "deviating", "changed", "reactive"

# Response settings ("knobs"). jam_width: assumed width of their all-in range (0..1);
# bet_f: multiplier on the width of their betting range; bluff_r: share of random hands in their aggression;
# value_mult: our value-size multiplier vs them; bluff_ok: how willing we are to bluff them (0..1).
_V1_K0 = {"jam_width": 0.5, "bet_f": 1.0, "bluff_r": 0.12, "value_mult": 1.0, "bluff_ok": 0.5}
_V1_PERSONALITY_KNOBS = {
    "shover":        {"jam_width": 1.0, "bet_f": 1.6, "bluff_r": 0.40, "value_mult": 1.3, "bluff_ok": 0.0},
    "maniac":        {"jam_width": 0.8, "bet_f": 1.8, "bluff_r": 0.45, "value_mult": 1.2, "bluff_ok": 0.2},
    "station":       {"jam_width": 0.6, "bet_f": 1.2, "bluff_r": 0.10, "value_mult": 1.6, "bluff_ok": 0.0},
    "nit":           {"jam_width": 0.12, "bet_f": 0.5, "bluff_r": 0.03, "value_mult": 0.6, "bluff_ok": 1.0},
    "tight_passive": {"jam_width": 0.15, "bet_f": 0.45, "bluff_r": 0.03, "value_mult": 0.8, "bluff_ok": 0.8},
    "loose_passive": {"jam_width": 0.5, "bet_f": 0.7, "bluff_r": 0.05, "value_mult": 1.4, "bluff_ok": 0.2},
    "folder":        {"jam_width": 0.3, "bet_f": 0.8, "bluff_r": 0.10, "value_mult": 0.8, "bluff_ok": 1.0},
    "balanced":      dict(_V1_K0),
    "unknown":       dict(_V1_K0),
}
# Out-of-character pool: responses chosen by the DIRECTION of the deviation (uses what we knew before).
_V1_OOC_POOL = {
    "aggression_up_respect":  {"jam_width": 0.25, "bet_f": 0.7, "bluff_r": 0.08, "value_mult": 1.0, "bluff_ok": 0.3},
    "aggression_up_calldown": {"jam_width": 0.7, "bet_f": 1.6, "bluff_r": 0.35, "value_mult": 1.1, "bluff_ok": 0.2},
    "tightening":             {"jam_width": 0.2, "bet_f": 0.5, "bluff_r": 0.05, "value_mult": 0.8, "bluff_ok": 0.8},
    "loosening":              {"jam_width": 0.6, "bet_f": 1.1, "bluff_r": 0.12, "value_mult": 1.3, "bluff_ok": 0.1},
    "robust":                 {"jam_width": 0.4, "bet_f": 1.0, "bluff_r": 0.20, "value_mult": 1.0, "bluff_ok": 0.3},
}
_V1_STATE_WEIGHT = {IN_CHARACTER: 1.0, DEVIATING: 0.6, CHANGED: 0.3, REACTIVE: 0.3}


class _V1Seat:
    def __init__(self):
        self.n = {s: 0.0 for s in _V1_STATS}      # decayed opportunities
        self.k = {s: 0.0 for s in _V1_STATS}      # decayed successes
        self.recent = {s: _v1_col.deque(maxlen=_V1_RECENT) for s in _V1_STATS}
        self.hands = 0
        self.state = IN_CHARACTER
        self.dev_since = None
        self.dev_direction = None
        self.calm_updates = 0
        self.showdowns = _v1_col.deque(maxlen=40)   # (strength 0..1, was_aggressor, hand_index)
        self.aggr_vs_me = _v1_col.deque(maxlen=_V1_RECENT)
        self.aggr_vs_field = _v1_col.deque(maxlen=_V1_RECENT)
        self.results = _v1_col.deque(maxlen=_V1_STOP_HANDS)  # our bb result in hands attributed to this seat
        self.stop_until = -1
        self.label = "unknown"
        self.pending_label, self.pending_count = None, 0
        self.history_states = _v1_col.deque(maxlen=20)

    def add(self, stat, x):
        self.n[stat] = self.n[stat] * _V1_DECAY + 1.0
        self.k[stat] = self.k[stat] * _V1_DECAY + (1.0 if x else 0.0)
        self.recent[stat].append(1 if x else 0)

    def rate(self, stat):
        return (self.k[stat] + _V1_PRIOR[stat] * _V1_PRIOR_K) / (self.n[stat] + _V1_PRIOR_K)

    def recent_rate(self, stat):
        r = self.recent[stat]
        return (sum(r) / len(r)) if r else None


class V1Profiles:
    """Layer 2: one shared stat profile per opponent seat, fed by the kit event layer."""

    def __init__(self):
        self.seats = {}
        self.me = None
        self.hand_index = 0
        self.big_blind = 20
        self.stack = 2000
        self._reset_hand()

    def _reset_hand(self):
        self.street = "preflop"
        self.facing_bet = False
        self.vpip_done = set()
        self.pfr_done = set()
        self.acted_pf = set()
        self.last_aggr = None           # (seat, street)
        self.board = []
        self.in_hand = set()            # seats that put voluntary chips in
        self.we_in = False

    def seat(self, s):
        if s not in self.seats:
            self.seats[s] = _V1Seat()
        return self.seats[s]

    # -------- events --------
    def observe(self, ev):
        t = ev.get("type")
        if t == "hand_start":
            self._reset_hand()
            self.hand_index += 1
            for s in range(len(ev.get("stacks") or [])):
                if s != self.me:
                    self.seat(s).hands += 1
        elif t == "board":
            self.street = ev.get("street", self.street)
            if ev.get("board"):
                self.board = list(ev["board"])
            self.facing_bet = False
        elif t == "action":
            self._on_action(ev)
        elif t == "showdown":
            self._on_showdown(ev)
        elif t == "hand_end":
            self._on_hand_end(ev)

    def _on_action(self, ev):
        seat, a = ev.get("seat"), ev.get("action")
        if seat is None or a in (None, "post", "small_blind", "big_blind"):
            return
        street = ev.get("street", self.street)
        if seat == self.me:
            if a in ("call", "raise"):
                self.we_in = True
            if a == "raise":
                self.facing_bet = True
                self.last_aggr = (seat, street)
            return
        st = self.seat(seat)
        if street == "preflop":
            if seat not in self.acted_pf:
                self.acted_pf.add(seat)
                st.add("vpip", a in ("call", "raise"))
                st.add("pfr", a == "raise")
                st.add("shove", a == "raise" and (ev.get("amount") or 0) >= 0.9 * self.stack)
            if a in ("call", "raise"):
                self.in_hand.add(seat)
        else:
            if a in ("raise", "call", "check"):
                st.add("aggr", a == "raise")
                (st.aggr_vs_me if self.we_in else st.aggr_vs_field).append(1 if a == "raise" else 0)
        if self.facing_bet and a in ("fold", "call", "raise"):
            st.add("fold_vs_bet", a == "fold")
        if a == "raise":
            self.facing_bet = True
            self.last_aggr = (seat, street)

    def _on_showdown(self, ev):
        hands = ev.get("hands") or {}
        board = self.board
        if len(board) < 5:
            return
        for seat, cards in hands.items():
            seat = int(seat)
            if seat == self.me or not cards:
                continue
            strength = _v1_strength(cards, board)
            was_aggr = bool(self.last_aggr and self.last_aggr[0] == seat)
            self.seat(seat).showdowns.append((strength, was_aggr, self.hand_index))

    def _on_hand_end(self, ev):
        deltas = ev.get("deltas") or []
        if self.me is not None and self.me < len(deltas) and self.we_in:
            bb = self.big_blind or 20
            mine = deltas[self.me] / bb
            # attribute our result to the opponent who won/lost most against us this hand
            opp = None
            if self.last_aggr and self.last_aggr[0] != self.me:
                opp = self.last_aggr[0]
            elif self.in_hand:
                opp = max(self.in_hand, key=lambda s: abs(deltas[s]) if s < len(deltas) else 0)
            if opp is not None:
                self.seat(opp).results.append(mine)
        for s, st in self.seats.items():
            self._update_state(s, st)

    # -------- layer 3: personality labels --------
    def classify(self, st):
        vpip, pfr, shove = st.rate("vpip"), st.rate("pfr"), st.rate("shove")
        aggr, fold = st.rate("aggr"), st.rate("fold_vs_bet")
        if st.hands < 8:
            return "unknown"
        if shove > 0.30:
            return "shover"
        if aggr > 0.55 or pfr > 0.35:
            return "maniac"
        if vpip > 0.45 and aggr < 0.25 and fold < 0.30:
            return "station"
        if vpip < 0.15:
            return "nit"
        if vpip < 0.30 and aggr < 0.25:
            return "tight_passive"
        if vpip > 0.40 and pfr < 0.10:
            return "loose_passive"
        if fold > 0.65:
            return "folder"
        return "balanced"

    # -------- layer 4: auto picker (surprise score + 4 states) --------
    def surprise(self, st):
        best, direction = 0.0, None
        for s in _V1_STATS:
            r = st.recent[s]
            if len(r) < 10:
                continue
            q = sum(r) / len(r)
            p = min(0.97, max(0.03, st.rate(s)))
            z = (q - p) / _v1_math.sqrt(p * (1 - p) / len(r))
            if abs(z) > abs(best):
                best, direction = z, (s, "up" if z > 0 else "down")
        return abs(best), direction

    def _reactive(self, st):
        a, b = st.aggr_vs_me, st.aggr_vs_field
        if len(a) < 12 or len(b) < 12:
            return False
        pa, pb = sum(a) / len(a), sum(b) / len(b)
        p = min(0.97, max(0.03, (sum(a) + sum(b)) / (len(a) + len(b))))
        z = (pa - pb) / _v1_math.sqrt(p * (1 - p) * (1 / len(a) + 1 / len(b)))
        return z > 3.0

    def _update_state(self, seat, st):
        z, direction = self.surprise(st)
        if st.state in (IN_CHARACTER, CHANGED, REACTIVE):
            if self._reactive(st):
                st.state = REACTIVE
            elif z >= _V1_Z_ENTER:
                st.state, st.dev_since, st.dev_direction, st.calm_updates = DEVIATING, st.hands, direction, 0
            elif st.state != IN_CHARACTER and z < _V1_Z_EXIT:
                st.state = IN_CHARACTER
        elif st.state == DEVIATING:
            if z < _V1_Z_EXIT:
                st.calm_updates += 1
                if st.calm_updates >= 3:           # it was noise: back to the personality
                    st.state = IN_CHARACTER
            else:
                st.calm_updates = 0
                if direction:
                    st.dev_direction = direction
                if st.hands - (st.dev_since or st.hands) >= _V1_CHANGE_HANDS:
                    self._relearn(st)              # persistent: a real change, relearn the bot
        new = self.classify(st)
        if new == st.label or st.label == "unknown" or st.state == CHANGED:
            st.label, st.pending_label, st.pending_count = new, None, 0
        elif new == st.pending_label:
            st.pending_count += 1
            if st.pending_count >= 3:                 # label hysteresis: must persist 3 updates
                st.label, st.pending_label, st.pending_count = new, None, 0
        else:
            st.pending_label, st.pending_count = new, 1
        st.history_states.append(st.state)
        # stop-loss
        if len(st.results) >= 15 and sum(st.results) <= _V1_STOP_BB and st.stop_until < self.hand_index:
            st.stop_until = self.hand_index + _V1_STOP_COOLDOWN
            st.results.clear()

    def _relearn(self, st):
        for s in _V1_STATS:
            r = st.recent[s]
            st.n[s] = float(len(r))
            st.k[s] = float(sum(r))
        st.showdowns = _v1_col.deque([x for x in st.showdowns if x[2] >= self.hand_index - 30], maxlen=40)
        st.state, st.dev_since, st.dev_direction = CHANGED, None, None

    # -------- knobs: blended response settings for one opponent --------
    def knobs(self, seat):
        st = self.seats.get(seat)
        if st is None or not _V1_USE_EXPLOIT:
            return dict(_V1_K0), 0.0, "unknown", IN_CHARACTER
        if not _V1_USE_PICKER:
            conf = st.hands / (st.hands + _V1_CONF_K)
            target = _V1_PERSONALITY_KNOBS.get(st.label, _V1_K0)
            return ({key: _V1_K0[key] + conf * (target[key] - _V1_K0[key]) for key in _V1_K0}, conf, st.label,
                    IN_CHARACTER)
        conf = st.hands / (st.hands + _V1_CONF_K)
        w = conf * _V1_STATE_WEIGHT.get(st.state, 0.3)
        if st.stop_until >= self.hand_index:
            w = 0.0
        if st.state == DEVIATING:
            target = _V1_OOC_POOL[self._ooc_choice(st)]
        else:
            target = _V1_PERSONALITY_KNOBS.get(st.label, _V1_K0)
        k = {key: _V1_K0[key] + w * (target[key] - _V1_K0[key]) for key in _V1_K0}
        # bluff share from showdowns (mixture model): junk shown after being the aggressor
        aggr_sd = [s for s, was_aggr, _ in st.showdowns if was_aggr]
        if len(aggr_sd) >= 4:
            junk = sum(1 for s in aggr_sd if s < 0.45) / len(aggr_sd)
            m = len(aggr_sd) / (len(aggr_sd) + 8.0)
            k["bluff_r"] = (1 - m) * k["bluff_r"] + m * junk
        return k, w, st.label, st.state

    def _ooc_choice(self, st):
        d = st.dev_direction
        if not d:
            return "robust"
        stat, way = d
        if stat in ("aggr", "pfr", "shove") and way == "up":
            junk_since = [s for s, was_aggr, h in st.showdowns
                          if was_aggr and st.dev_since is not None and h >= self.hand_index - (st.hands - st.dev_since)]
            if sum(1 for s in junk_since if s < 0.45) >= 2:
                return "aggression_up_calldown"
            return "aggression_up_respect"
        if (stat == "vpip" and way == "down") or (stat in ("aggr", "pfr") and way == "down"):
            return "tightening"
        if (stat == "vpip" and way == "up") or (stat == "fold_vs_bet" and way == "down"):
            return "loosening"
        if stat == "fold_vs_bet" and way == "up":
            return "tightening"
        return "robust"

    def fold_prob(self, seat):
        st = self.seats.get(seat)
        return st.rate("fold_vs_bet") if st else _V1_PRIOR["fold_vs_bet"]

    def describe(self):
        return {s: {"label": st.label, "state": st.state, "hands": st.hands,
                    "vpip": round(st.rate("vpip"), 2), "aggr": round(st.rate("aggr"), 2),
                    "fold_vs_bet": round(st.rate("fold_vs_bet"), 2), "shove": round(st.rate("shove"), 2)}
                for s, st in sorted(self.seats.items())}


EXTRA_TRACKERS.append(V1Profiles)


# -------- shared helpers (equity vs ranges within the time budget) --------
def _v1_strength(cards, board, samples=40):
    """Fraction of random opponent holdings that this hand beats on the final board (ties = half)."""
    try:
        h = [_card(c) for c in cards]
        b = [_card(c) for c in board[:5]]
        dead = set(h) | set(b)
        deck = [c for c in range(52) if c not in dead]
        me = _evaluate(h + b)
        rng = random.Random(hash(tuple(h + b)) & 0xFFFF)
        score = 0.0
        for _ in range(samples):
            o = rng.sample(deck, 2)
            v = _evaluate(o + b)
            score += 1.0 if me > v else (0.5 if me == v else 0.0)
        return score / samples
    except Exception:
        return 0.5


def _v1_class_pct():
    """Percentile (0 = best) of each 169 hand class by heads-up equity, weighted by combos."""
    items = []
    R = "23456789TJQKA"
    for key, eq in _PF_EQ.items():
        if isinstance(key, tuple):                        # (high rank, low rank, suited)
            hi, lo, suited = key
            key = R[hi] * 2 if hi == lo else R[hi] + R[lo] + ("s" if suited else "o")
        combos = 6 if len(key) == 2 else (4 if key.endswith("s") else 12)
        items.append((eq, key, combos))
    items.sort(reverse=True)
    out, cum = {}, 0
    for eq, key, combos in items:
        out[key] = (cum + combos / 2.0) / 1326.0
        cum += combos
    return out


try:
    _V1_PCT = _v1_class_pct()
except Exception:
    _V1_PCT = {}


def _v1_key(c1, c2):
    r1, r2 = c1 >> 2, c2 >> 2
    if r1 < r2:
        r1, r2, c1, c2 = r2, r1, c2, c1
    R = "23456789TJQKA"
    if r1 == r2:
        return R[r1] * 2
    return R[r1] + R[r2] + ("s" if (c1 & 3) == (c2 & 3) else "o")


def _v1_equity(hole, board, ranges, rng, deadline, max_samples=36):
    """MC equity vs a list of (width f, random share r) ranges, one per live opponent. Ties = split."""
    known = set(hole + board)
    deck = [c for c in range(52) if c not in known]
    missing = 5 - len(board)
    total = 0.0
    n = 0
    for _ in range(max_samples):
        if n >= 4 and time.perf_counter() >= deadline:
            break
        avail = deck[:]
        rng.shuffle(avail)
        idx = 0
        opps = []
        ok = True
        for f, r in ranges:
            got = None
            for _try in range(8):
                if idx + 2 > len(avail):
                    break
                c1, c2 = avail[idx], avail[idx + 1]
                idx += 2
                if f >= 0.999 or rng.random() < r or _V1_PCT.get(_v1_key(c1, c2), 0.5) <= f:
                    got = [c1, c2]
                    break
            if got is None:
                ok = False
                break
            opps.append(got)
        if not ok or idx + missing > len(avail):
            continue
        full = board + avail[idx: idx + missing]
        me = _evaluate(hole + full)
        best, ties = me, 1
        lost = False
        for o in opps:
            v = _evaluate(o + full)
            if v > best:
                lost = True
                break
            if v == best:
                ties += 1
        if not lost:
            total += 1.0 / ties
        n += 1
    return (total / n) if n else 0.5, n


def _v1_profiles(agent, state=None):
    p = agent.trackers.get("V1Profiles")
    if p is not None:
        p.me = state.get("seat", getattr(agent, "seat", None)) if state else getattr(agent, "seat", None)
        p.stack = int(agent.info.get("starting_stack", 2000) or 2000)
        if state:
            p.big_blind = int(S(state, "big_blind", p.big_blind) or p.big_blind)
    return p


def _v1_live_opps(state):
    me = state.get("seat")
    return [i for i, f in enumerate(state.get("folded") or []) if not f and i != me]


# ===========================================================================================
# HOOKS (layer 1 baseline + layer 3 responses, blended by the picker's knobs)
# ===========================================================================================
def hook_facing_allin(agent, state, ctx):
    """Delegate to the tournament shove-defense plug-in unless the jammer is confidently tight."""
    prof = _v1_profiles(agent, state)
    if prof is not None and S(state, "street") == "preflop":
        bets = S(state, "bets") or []
        if bets:
            jammer = max(range(len(bets)), key=lambda i: bets[i])
            k, w, label, st = prof.knobs(jammer)
            if w > 0.35 and k["jam_width"] < 0.3:
                key = _v1_key(*ctx["hole"])
                pct = _V1_PCT.get(key, 0.5)
                callers = sum(1 for i, b in enumerate(bets) if b >= bets[jammer] and i not in (jammer, state.get("seat")))
                limit = max(0.025, k["jam_width"] * (0.45 if callers == 0 else 0.25))
                if pct <= limit:
                    return {"action": "call"} if "call" in S(state, "legal_actions", []) else None
                return {"action": "fold"} if "fold" in S(state, "legal_actions", []) else None
    return _cand_facing_allin(agent, state, ctx)


def hook_preflop(agent, state, ctx):
    return _cand_preflop(agent, state, ctx)


def hook_betting(agent, state, ctx):
    """Nothing to call postflop. Multiway: tournament plug-in (+ P(all fold) bluff gate). Heads-up: v1 rules."""
    prof = _v1_profiles(agent, state)
    opps = _v1_live_opps(state)
    legal = S(state, "legal_actions", [])
    if "raise" not in legal:
        return None
    if len(opps) >= 2:
        return _cand_betting_mw(agent, state, ctx)
    if not opps:
        return None
    v = opps[0]
    k, w, label, st = prof.knobs(v) if prof else (dict(_V1_K0), 0.0, "unknown", IN_CHARACTER)
    deadline = ctx["started"] + _V1_MC_SECONDS
    eq, _ = _v1_equity(ctx["hole"], ctx["board"], [(1.0, 0.0)], agent.rng, deadline)
    ctx["v1_eq"] = eq
    if eq >= 0.62:
        frac = (0.66 if eq < 0.8 else 0.8) * k["value_mult"]
        return {"action": "raise", "amount": agent.size(state, ctx, "value", frac)}
    if eq < 0.35 and k["bluff_ok"] > 0.0:
        p_fold = prof.fold_prob(v) if prof else 0.45
        frac = 0.5
        need = frac / (1 + frac)
        if p_fold > need + 0.07 and agent.rng.random() < k["bluff_ok"]:
            return {"action": "raise", "amount": agent.size(state, ctx, "bluff", frac)}
    return {"action": "check"}


def hook_facing_bet(agent, state, ctx):
    """Facing a (non all-in) postflop bet: price exactly, equity vs the bettor's estimated range."""
    prof = _v1_profiles(agent, state)
    legal = S(state, "legal_actions", [])
    bets = S(state, "bets") or []
    pot = S(state, "pot")
    to_call = S(state, "to_call", 0) or 0
    if not bets or pot is None:
        return None
    me = state.get("seat")
    opps = _v1_live_opps(state)
    bettor = max(range(len(bets)), key=lambda i: bets[i])
    k, w, label, st = prof.knobs(bettor) if prof else (dict(_V1_K0), 0.0, "unknown", IN_CHARACTER)
    size_frac = to_call / max(1, pot - to_call)          # bet as a fraction of the pot before it
    base_f = 0.65 if size_frac <= 0.4 else (0.45 if size_frac <= 1.0 else 0.32)
    if S(state, "raises_this_street", 0) and S(state, "raises_this_street", 0) >= 2:
        base_f *= 0.6                                    # raise/re-raise: narrower
    f = max(0.04, min(1.0, base_f * k["bet_f"]))
    ranges = [(f, k["bluff_r"])] + [(0.7, 0.0) for o in opps if o != bettor][:3]  # cap work in big pots
    deadline = ctx["started"] + _V1_MC_SECONDS
    if time.perf_counter() - ctx["started"] > 0.005:
        return None                                       # time guard: fall back to the cheap default policy
    eq, _ = _v1_equity(ctx["hole"], ctx["board"], ranges, agent.rng, deadline)
    pot_odds = to_call / (pot + to_call)
    if eq >= 0.72 and "raise" in legal and len(opps) <= 2:
        frac = 0.75 * k["value_mult"]
        return {"action": "raise", "amount": agent.size(state, ctx, "raise_value", frac)}
    if eq >= pot_odds + 0.03:
        return {"action": "call"} if "call" in legal else {"action": "check"}
    return {"action": "fold"} if "fold" in legal else {"action": "check"}


def hook_sizing(agent, state, ctx, intent):
    """Pot-fraction sizes scaled by the table's value multiplier; near-stack sizes become all-in."""
    prof = _v1_profiles(agent, state)
    hi = state.get("max_raise_to")
    lo = state.get("min_raise_to")
    if hi is None or lo is None:
        return None
    base = {"value": 0.75, "thin_value": 0.55, "bluff": 0.5, "probe": 0.33,
            "raise_value": 0.75, "raise_bluff": 0.6}.get(intent, 0.6)
    mult = 1.0
    if prof is not None:
        opps = _v1_live_opps(state)
        if opps:
            mult = sum(prof.knobs(o)[0]["value_mult"] for o in opps) / len(opps)
    if intent in ("bluff", "probe", "raise_bluff"):
        mult = 1.0                                        # bluffs use standard sizes (no size tells)
    amt = pot_raise_to(state, base * mult)
    if amt is None:
        return None
    if amt >= 0.8 * hi:
        amt = hi
    return int(max(lo, min(hi, amt)))
