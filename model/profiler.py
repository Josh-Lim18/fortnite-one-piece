"""Online layer 2 opponent model: for each seat, the chance it folds, calls or raises in a situation, which
fitted type it is, and what hands it holds after an action. Standard library only.

To paste into bot.py: put FITTED from model/fitted.py and everything below the import block here beside the
bot's own helpers (the bot already defines card, hand_pct and score), then in the bot:
    on_table_start: self.model = Profiler(info["num_players"], FITTED)
    on_hand_end:    self.model.observe_hand(summary, self.seat)
"""
import math
import os
import random
import sys
from bisect import bisect_left, bisect_right

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from bot import card, hand_pct, score  # noqa: E402  (bot.py defines these itself)

STREETS = ("preflop", "flop", "turn", "river")
ACTIONS = {"fold": 0, "check": 1, "call": 1, "raise": 2}  # check and call are both the passive "call"
CELLS = 4 * 5 * 3  # street x bet-size bucket x raises this street (0, 1, 2+)
BUCKETS = 10       # hand-strength buckets, 0 weakest
HALF_LIFE = 150.0  # hands for an observation's weight to halve, so a change of style is re-read
RANGE_M = 10.0     # a seat's own showdowns outweigh its type's range after this many
SAMPLES = 40       # random hands a postflop hand is ranked against online


def size_bucket(to_call, pot):
    """The bet faced as a share of the pot: 0 none, 1 under 0.35, 2 to 0.8, 3 to 1.3, 4 over."""
    if to_call <= 0:
        return 0
    x = to_call / pot
    return 1 if x < 0.35 else 2 if x < 0.8 else 3 if x < 1.3 else 4


def cell(street, size, raises):
    return (street * 5 + size) * 3 + min(raises, 2)


def decisions(history, n):
    """Replay a hand's history (state["history"] format); yields (seat, street index, size bucket, raises
    this street, players in, action index) for each fold, check, call or raise."""
    bets, pot, street, raises, folded = [0] * n, 0, "preflop", 0, 0
    for h in history:
        seat, action, amount = h["seat"], h["action"], h["amount"]
        if h["street"] != street:
            street, bets, raises = h["street"], [0] * n, 0
        if action in ("small_blind", "big_blind"):
            bets[seat] += amount
            pot += amount
            continue
        yield seat, STREETS.index(street), size_bucket(max(bets) - bets[seat], pot), raises, n - folded, ACTIONS[action]
        if action == "raise":
            pot += amount - bets[seat]
            bets[seat] = amount
            raises += 1
        elif action == "call":
            pot += amount
            bets[seat] += amount
        elif action == "fold":
            folded += 1


def showdown_buckets(shown, board, rng, samples):
    """{seat: [bucket per street]} for shown hands: preflop percentile among starting hands, postflop the
    percentile against `samples` random hands on that street's board."""
    hole = {s: [card(c) for c in cs] for s, cs in shown.items()}
    board = [card(c) for c in board]
    out = {s: [min(BUCKETS - 1, int(BUCKETS * (1 - hand_pct(*h))))] for s, h in hole.items()}
    used = set(board) | {c for h in hole.values() for c in h}
    deck = [c for c in range(52) if c not in used]
    for k in (3, 4, 5):
        if len(board) < k:
            break
        b = board[:k]
        ref = sorted(score(rng.sample(deck, 2) + b) for _ in range(samples))
        for s, h in hole.items():
            v = score(h + b)
            pct = (bisect_left(ref, v) + bisect_right(ref, v)) / (2.0 * samples)
            out[s].append(min(BUCKETS - 1, int(BUCKETS * pct)))
    return out


class Profiler:
    def __init__(self, n, fitted, counts=True, types=True):
        """`counts` and `types` off give the weaker versions evaluate.py scores against."""
        f = fitted
        self.pop, self.pop_m, self.types_p, self.type_m = f["pop"], f["pop_m"], f["types"], f["type_m"]
        self.prior = [math.log(w) for w in f["type_prior"]]
        self.ranges = f["ranges"]
        self.log_types = [[[math.log(max(p, 1e-3)) for p in c] for c in t] for t in f["types"]]
        self.use_counts, self.use_types = counts, types
        self.k = len(f["type_prior"])
        self.hand = 0
        self.counts = [[0.0] * (CELLS * 3) for _ in range(n)]
        self.ll = [[0.0] * self.k for _ in range(n)]
        self.shown = [[[[0.0] * BUCKETS for _ in range(2)] for _ in STREETS] for _ in range(n)]
        self.rng = random.Random(0)

    def observe(self, seat, situation, action, hand):
        """One action (0 fold, 1 check or call, 2 raise) by `seat` in `situation` (a cell()) at hand number `hand`."""
        self.hand = hand
        w = 2.0 ** (hand / HALF_LIFE)  # stored weights grow instead of old ones shrinking; the ratio is the decay
        self.counts[seat][situation * 3 + action] += w
        ll = self.ll[seat]
        for t in range(self.k):
            ll[t] += w * self.log_types[t][situation][action]

    def observe_showdown(self, seat, street, action, bucket):
        """`seat` showed a hand in `bucket` after its last action (1 or 2) on `street`."""
        self.shown[seat][street][action - 1][bucket] += 1

    def observe_hand(self, summary, me=None):
        """Feed one finished hand from on_hand_end's summary; `me` is our own seat, left out."""
        hand, last = summary["hand_number"], {}
        for seat, street, size, raises, _, action in decisions(summary["history"], len(self.counts)):
            if seat != me:
                self.observe(seat, cell(street, size, raises), action, hand)
                last[seat, street] = action
        shown = {int(s): c for s, c in summary["shown"].items() if int(s) != me}
        if shown:
            for seat, buckets in showdown_buckets(shown, summary["board"], self.rng, SAMPLES).items():
                for street, b in enumerate(buckets):
                    if last.get((seat, street), 0):
                        self.observe_showdown(seat, street, last[seat, street], b)

    def type_posterior(self, seat):
        decay = 2.0 ** (-self.hand / HALF_LIFE)
        lp = [p + decay * l for p, l in zip(self.prior, self.ll[seat])]
        top = max(lp)
        w = [math.exp(x - top) for x in lp]
        z = sum(w)
        return [x / z for x in w]

    def predict(self, seat, situation):
        """(fold, call, raise) probabilities for `seat`'s next action in `situation`."""
        if self.use_types:
            w = self.type_posterior(seat)
            mean = [sum(w[t] * self.types_p[t][situation][a] for t in range(self.k)) for a in (0, 1, 2)]
            m = self.type_m[situation]
        else:
            mean, m = self.pop[situation], self.pop_m[situation]
        if not self.use_counts:
            z = sum(mean)
            return tuple(p / z for p in mean)
        decay = 2.0 ** (-self.hand / HALF_LIFE)
        c = self.counts[seat]
        i = situation * 3
        n = [c[i] * decay, c[i + 1] * decay, c[i + 2] * decay]
        z = sum(n) + m * sum(mean)
        return tuple((n[a] + m * mean[a]) / z for a in (0, 1, 2))

    def range(self, seat, street, action):
        """Distribution over hand-strength buckets (0 weakest) of `seat`'s hand after `action` (1 or 2) on `street`."""
        w = self.type_posterior(seat)
        own = self.shown[seat][street][action - 1]
        n = sum(own)
        mix = [sum(w[t] * self.ranges[t][street][action - 1][b] for t in range(self.k)) for b in range(BUCKETS)]
        z = n + RANGE_M * sum(mix)  # the fitted ranges are rounded, so sum(mix) is only near 1
        return [(own[b] + RANGE_M * mix[b]) / z for b in range(BUCKETS)]
