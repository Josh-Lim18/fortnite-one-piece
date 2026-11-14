"""A bot whose play is set by a profile calibrated to one real team (tools/field_fit.py).

Preflop it plays the top share of hands by position and by what it faces; postflop it compares Monte Carlo equity
against random hands with thresholds, bets bigger the stronger it is, and calls on pot odds plus a margin.

    Agent = make_agent({"open_BTN": 0.45, "call_margin": 0.1})   # keys left out fall back to DEFAULT
"""
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(HERE, "..", "..", "kit"))
from clone_base import call, passive, pct, raise_to  # noqa: E402
from engine.cards import evaluate, to_int  # noqa: E402

SHOVE = 800    # chips: facing a preflop raise to this much is facing a shove
TRIALS = 48    # Monte Carlo deals per postflop equity estimate
POSITIONS = ("EP", "MP", "CO", "BTN", "SB", "BB")

# Every profile key and its value for an average seat of the counted field.
DEFAULT = {
    **{"open_" + p: v for p, v in zip(POSITIONS, (0.12, 0.15, 0.22, 0.32, 0.22, 0.08))},
    "limp": 0.02,          # unraised, beyond the raising range: share of hands that calls
    "shove": 0.002,        # unraised: share of hands that shoves
    "open_bb": 2.8,        # first raise, in big blinds, plus one per limper
    "threebet": 0.05,      # facing one raise: share of hands that re-raises to threebet_x times it
    "threebet_x": 3.0,
    "call_open": 0.08,     # facing one raise: share of hands, beyond the re-raising ones, that calls
    "fourbet": 0.02,       # facing two or more raises: share of hands that raises again
    "call_3bet": 0.05,     # facing two or more raises: share of hands, beyond those, that calls
    "call_allin": 0.06,    # facing a raise to SHOVE chips or more: share of hands that calls
    "val_flop": 0.62,      # checked to: bet with at least this equity, by street
    "val_turn": 0.66,
    "val_river": 0.70,
    "cbluff": 0.30,        # flop, as the last preflop raiser, below val_flop: chance it bets anyway
    "call_margin": 0.25,   # facing a bet: call with equity of call_slope * pot odds + call_margin
    "call_slope": 1.0,
    "raise_eq": 0.85,      # facing a bet: raise with this equity
    # Bet sizes as a share of the pot, five quantiles per street; a hand picks one by how far above val it is.
    "sizes_flop": (0.33, 0.5, 0.6, 0.75, 1.0),
    "sizes_turn": (0.33, 0.5, 0.6, 0.75, 1.0),
    "sizes_river": (0.33, 0.5, 0.6, 0.75, 1.0),
}


def position(seat, button, n):
    """Same buckets as tools/analyze.position, which the calibration targets are measured in."""
    off = (seat - button) % n
    return {n - 1: "CO", 0: "BTN", 1: "SB", 2: "BB"}.get(off, "EP" if off < (n + 2) // 2 else "MP")


def equity(rng, hole, board, opponents, trials=TRIALS):
    """Share of pots won at showdown against `opponents` random hands, the board dealt out."""
    known = hole + board
    deck = [c for c in range(52) if c not in known]
    missing = 5 - len(board)
    need = missing + 2 * opponents
    won = 0.0
    for _ in range(trials):
        draw = rng.sample(deck, need)
        full = board + draw[:missing]
        mine = evaluate(hole + full)
        best = max(evaluate(draw[k:k + 2] + full) for k in range(missing, need, 2))
        won += 1.0 if mine > best else 0.5 if mine == best else 0.0
    return won / trials


def make_agent(profile):
    unknown = set(profile) - set(DEFAULT)
    if unknown:
        raise KeyError("unknown profile keys: %s" % sorted(unknown))
    p = dict(DEFAULT, **profile)

    class Agent:
        def __init__(self):
            self.rng = random.Random()
            self.cache = {}

        def act(self, state):
            if state["street"] == "preflop":
                return self._preflop(state)
            return self._postflop(state)

        def _preflop(self, state):
            q, top, bb = pct(state["hole_cards"]), max(state["bets"]), state["big_blind"]
            raises = [h["seat"] for h in state["history"] if h["street"] == "preflop" and h["action"] == "raise"]
            if state["to_call"] and top >= SHOVE:
                return call(state) if q <= p["call_allin"] else passive(state)
            if not raises:
                if q <= p["shove"]:
                    return {"action": "all_in"}
                pos = position(state["seat"], state["button"], len(state["stacks"]))
                limpers = sum(1 for h in state["history"] if h["action"] == "call")
                if q <= p["open_" + pos]:
                    return raise_to(state, (p["open_bb"] + limpers) * bb)
                return call(state) if q <= p["open_" + pos] + p["limp"] and pos != "BB" else passive(state)
            if len(raises) == 1:
                if q <= p["threebet"]:
                    return raise_to(state, p["threebet_x"] * top)
                return call(state) if q <= p["threebet"] + p["call_open"] else passive(state)
            if q <= p["fourbet"]:
                return raise_to(state, 2.3 * top)
            return call(state) if q <= p["fourbet"] + p["call_3bet"] else passive(state)

        def _postflop(self, state):
            street, pot, to_call, top = state["street"], state["pot"], state["to_call"], max(state["bets"])
            live = sum(1 for i, f in enumerate(state["folded"]) if not f and i != state["seat"])
            key = (tuple(state["hole_cards"]), tuple(state["board"]), min(live, 2))
            if key not in self.cache:
                self.cache = {key: equity(self.rng, [to_int(c) for c in key[0]], [to_int(c) for c in key[1]], key[2])}
            eq = self.cache[key]
            sizes = p["sizes_" + street]
            val = p["val_" + street]
            u = (eq - val) / (1.0 - val) if eq >= val and val < 1 else self.rng.random()
            share = sizes[min(len(sizes) - 1, int(max(u, 0.0) * len(sizes)))]
            if not to_call:
                pf = [h["seat"] for h in state["history"] if h["street"] == "preflop" and h["action"] == "raise"]
                cbet = street == "flop" and pf and pf[-1] == state["seat"]
                if eq >= val or (cbet and self.rng.random() < p["cbluff"]):
                    return raise_to(state, top + share * pot)
                return passive(state)
            if eq >= p["raise_eq"]:
                return raise_to(state, top + share * (pot + to_call))
            odds = to_call / (pot + to_call)
            return call(state) if eq >= p["call_slope"] * odds + p["call_margin"] else passive(state)

    Agent.profile = p
    return Agent
