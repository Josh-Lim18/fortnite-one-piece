"""Tight-aggressive Hold'em bot that profiles each seat and shifts its thresholds to exploit it.

One file, standard library only: the tournament sandbox loads nothing else.
"""
import gc
import random
import time

# Every tunable number lives here so tools/tune.py can search them.
PARAMS = {
    # Share of hands opened when nobody has raised, by players still to act behind.
    "open": {1: 0.40, 2: 0.42, 3: 0.28, 4: 0.22, 5: 0.17, 6: 0.14, 7: 0.12},
    "open_bb": 3.0,            # open-raise size in big blinds, plus one per limper
    "iso_raise": 0.12,         # big blind raises limpers with this share of hands
    "threebet_r": 0.30,        # re-raise when our hand is in this top share of the raiser's range
    "call_r": 0.85,            # call a raise when in this top share of the raiser's range
    "call_cap": 0.22,          # ...but never wider than this share of all hands
    "stackoff_r": 0.50,        # put the stack in preflop when in this top share of their range
    "big_bet": 0.40,           # a bet this share of the starting stack counts as a shove
    "setmine_cost": 0.05,      # call with any pair when it costs at most this share of the stack
    "value": 0.62,             # bet when equity is above this
    "big_value": 0.80,         # bet big / raise when equity is above this
    "bet_frac": 0.66,
    "big_bet_frac": 0.90,
    "call_margin": 0.06,       # equity needed beyond pot odds against a constant bettor
    "passive_margin": 0.16,    # extra equity needed against a seat that rarely bets
    "bluff_fold_rate": 0.55,   # bluff heads-up only when the seat folds to bets this often
    "bluff_freq": 0.60,
    "bluff_frac": 0.50,
    "risk": 0.0,               # added to every stack-off threshold; raise it to chase variance
    "prior_hands": 12.0,       # how many hands of "average player" each seat's stats start with
    "prior_vpip": 0.30,
    "prior_pfr": 0.15,
    "prior_shove": 0.03,
    "prior_aggr": 0.30,
    "prior_fold": 0.45,
    "trials": 60,              # Monte Carlo rollouts per postflop decision
    "decision_ms": 1.5,        # stop rolling out after this long
    "round_budget_s": 3.0,     # own thinking time after which rollouts are cut to a quarter
}

RANKS = "23456789TJQKA"
SUITS = "cdhs"
ORDER = (
    "AA KK QQ JJ TT 99 AKs 88 AQs AKo AJs AQo KQs ATs KJs 77 AJo KTs QJs A9s ATo KQo 66 A8s KJo K9s "
    "A9o A7s QTs A5s JTs A4s QJo KTo Q9s A6s QTo A8o K8s K9o 55 J9s A5o Q9o JTo A7o Q8s K6s T9s A6o "
    "A3s K7s K8o A2s A4o J8s T8s K5s 44 A3o 98s T9o Q7s J9o K6o K3s Q5s A2o J7s Q8o K4s T7s K7o K5o "
    "J8o Q6s K2s Q4s 87s Q7o K4o T8o 98o 97s Q3s 33 Q2s J5s T6s J7o J6s J3s 96s Q6o Q5o T7o J4s K3o "
    "87o 86s 22 76s 97o K2o 95s 85s Q4o 75s T5s J2s T4s J6o T3s Q3o 94s 96o Q2o 65s J5o J4o T6o 76o "
    "86o 92s 53s T2s 64s J3o 84s 54s 74s 85o 93s T4o 75o T5o 95o 65o 73s J2o 82s 83s 63s 43s 54o 64o "
    "72s 42s T2o 94o 52s T3o 74o 62s 32s 93o 92o 84o 53o 63o 43o 83o 82o 73o 42o 52o 62o 72o 32o"
)


def _build_pct():
    """PCT[hi * 26 + lo * 2 + suited] = share of all starting hands at least this good."""
    pct = [1.0] * (13 * 26)
    seen = 0
    for name in ORDER.split():
        hi, lo = RANKS.index(name[0]), RANKS.index(name[1])
        seen += 6 if hi == lo else 4 if name[2] == "s" else 12
        suited = 1 if name[-1] == "s" else 0
        pct[hi * 26 + lo * 2 + suited] = pct[lo * 26 + hi * 2 + suited] = seen / 1326.0
    return pct


def _build_masks():
    """Per 13-bit rank mask: top rank of a straight (or -1), and its five highest ranks packed."""
    straight, top5 = [-1] * 8192, [0] * 8192
    for mask in range(8192):
        wheel = (mask << 1) | (mask >> 12 & 1)  # ace also plays low
        for top in range(13, 3, -1):
            if (wheel >> (top - 4)) & 31 == 31:
                straight[mask] = top - 1
                break
        packed, n = 0, 0
        for r in range(12, -1, -1):
            if mask >> r & 1 and n < 5:
                packed = packed << 4 | r
                n += 1
        top5[mask] = packed
    return straight, top5


PCT = _build_pct()
STRAIGHT, TOP5 = _build_masks()
DECK = list(range(52))


def card(text):
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def hand_pct(c1, c2):
    return PCT[(c1 >> 2) * 26 + (c2 >> 2) * 2 + (1 if (c1 & 3) == (c2 & 3) else 0)]


def score(cards):
    """Strength of the best five of 5-7 cards as one int; higher wins."""
    counts = [0] * 13
    suit_n = [0, 0, 0, 0]
    suit_mask = [0, 0, 0, 0]
    mask = 0
    for c in cards:
        r = c >> 2
        s = c & 3
        counts[r] += 1
        suit_n[s] += 1
        suit_mask[s] |= 1 << r
        mask |= 1 << r
    # Seven cards cannot hold a flush together with quads or a full house.
    for s in (0, 1, 2, 3):
        if suit_n[s] >= 5:
            fm = suit_mask[s]
            sh = STRAIGHT[fm]
            return (8 << 20 | sh) if sh >= 0 else (5 << 20 | TOP5[fm])
    quad = -1
    trips = []
    pairs = []
    singles = []
    for r in range(12, -1, -1):
        n = counts[r]
        if n == 1:
            singles.append(r)
        elif n == 2:
            pairs.append(r)
        elif n == 3:
            trips.append(r)
        elif n == 4:
            quad = r
    if quad >= 0:
        kicker = max(r for r in range(13) if counts[r] and r != quad)
        return 7 << 20 | quad << 4 | kicker
    if trips and (len(trips) > 1 or pairs):
        second = max(trips[1] if len(trips) > 1 else -1, pairs[0] if pairs else -1)
        return 6 << 20 | trips[0] << 4 | second
    sh = STRAIGHT[mask]
    if sh >= 0:
        return 4 << 20 | sh
    if trips:
        return 3 << 20 | trips[0] << 8 | singles[0] << 4 | singles[1]
    if len(pairs) >= 2:
        kicker = singles[0] if singles else -1
        if len(pairs) > 2 and pairs[2] > kicker:
            kicker = pairs[2]
        return 2 << 20 | pairs[0] << 8 | pairs[1] << 4 | kicker
    if pairs:
        return 1 << 20 | pairs[0] << 12 | singles[0] << 8 | singles[1] << 4 | singles[2]
    return TOP5[mask]


class Seat:
    """Running counts of what one opponent does."""

    __slots__ = ("hands", "vpip", "pfr", "shove", "bets", "passive", "folds", "continues")

    def __init__(self):
        self.hands = self.vpip = self.pfr = self.shove = 0
        self.bets = self.passive = self.folds = self.continues = 0


class Agent:
    def __init__(self, params=None):
        self.p = dict(PARAMS, **(params or {}))
        self.rng = random.Random()
        self.seats = []
        self.stack = 2000
        self.spent = 0.0
        gc.disable()  # a collection pause can blow the 10 ms limit

    def on_table_start(self, info):
        self.seats = [Seat() for _ in range(info["num_players"])]
        self.stack = info["starting_stack"]

    # ------------------------------------------------------------ profiling
    def _rate(self, count, total, prior):
        k = self.p["prior_hands"]
        return (count + prior * k) / (total + k)

    def _seat(self, i):
        while len(self.seats) <= i:
            self.seats.append(Seat())
        return self.seats[i]

    def on_hand_end(self, summary):
        big = self.p["big_bet"] * self.stack
        entered, raised, shoved = set(), set(), set()
        street, bet_open = "preflop", False
        for h in summary["history"]:
            a, i = h["action"], h["seat"]
            if h["street"] != street:
                street, bet_open = h["street"], False
            if a in ("small_blind", "big_blind"):
                continue
            s = self._seat(i)
            if street == "preflop":
                if a in ("call", "raise"):
                    entered.add(i)
                if a == "raise":
                    raised.add(i)
                    if h["amount"] >= big:
                        shoved.add(i)
                continue
            if bet_open:
                if a == "fold":
                    s.folds += 1
                else:
                    s.continues += 1
            if a == "raise":
                s.bets += 1
                bet_open = True
            elif a in ("check", "call"):
                s.passive += 1
        for i in range(len(summary["stacks"])):
            s = self._seat(i)
            s.hands += 1
            s.vpip += i in entered
            s.pfr += i in raised
            s.shove += i in shoved

    # --------------------------------------------------------------- acting
    def act(self, state):
        t0 = time.perf_counter()
        try:
            if state["street"] == "preflop":
                move = self._preflop(state)
            else:
                move = self._postflop(state, t0)
        except Exception:
            move = self._passive(state)
        self.spent += time.perf_counter() - t0
        return move

    @staticmethod
    def _passive(state):
        return {"action": "check" if "check" in state["legal_actions"] else "fold"}

    @staticmethod
    def _call(state):
        return {"action": "call" if "call" in state["legal_actions"] else "check"}

    def _raise(self, state, target):
        if "raise" not in state["legal_actions"]:
            return self._call(state)
        lo, hi = state["min_raise_to"], state["max_raise_to"]
        target = int(target)
        if target >= 0.6 * hi:
            target = hi  # past this point a fold later is never right, so commit now
        return {"action": "raise", "amount": max(lo, min(target, hi))}

    def _preflop(self, state):
        p = self.p
        me, n, bb = state["seat"], len(state["stacks"]), state["big_blind"]
        c1, c2 = (card(c) for c in state["hole_cards"])
        pct = hand_pct(c1, c2)
        bets, to_call = state["bets"], state["to_call"]
        top_bet = max(bets)

        raises, limpers, raiser, callers_of_raise = 0, 0, -1, 0
        for h in state["history"]:
            if h["action"] == "raise":
                raises += 1
                raiser = h["seat"]
                callers_of_raise = 0
            elif h["action"] == "call":
                if raises:
                    callers_of_raise += 1
                else:
                    limpers += 1

        if raises == 0:
            behind = (state["button"] - me) % n
            behind = 1 if behind == n - 1 else 0 if behind == n - 2 else behind + 2
            limit = p["iso_raise"] if behind == 0 else p["open"].get(behind, 0.12)
            if pct <= limit:
                return self._raise(state, (p["open_bb"] + limpers) * bb)
            return self._passive(state)

        opp = self._seat(raiser)
        pfr = self._rate(opp.pfr, opp.hands, p["prior_pfr"])
        shove = self._rate(opp.shove, opp.hands, p["prior_shove"])
        if top_bet >= p["big_bet"] * self.stack:
            width = shove
        elif raises >= 2:
            width = max(pfr * 0.3, shove)
        else:
            width = pfr
        width = max(width, 0.02)
        depth = pct / width  # 0 = top of the raiser's range, 1 = its bottom
        crowd = 0.7 ** callers_of_raise  # callers behind a raise hold real hands too

        committed = top_bet >= p["big_bet"] * self.stack or to_call >= 0.3 * self.stack
        if depth <= (p["stackoff_r"] + p["risk"]) * crowd:
            if committed:
                return {"action": "all_in"}
            if depth <= p["threebet_r"] * crowd:
                return self._raise(state, top_bet * 3 + to_call * callers_of_raise)
        if committed:
            return self._passive(state)
        cheap = to_call <= p["setmine_cost"] * self.stack
        if cheap and (c1 >> 2) == (c2 >> 2):
            return self._call(state)
        if to_call <= 0.08 * self.stack and pct <= min(p["call_r"] * width, p["call_cap"]):
            return self._call(state)
        return self._passive(state)

    def _postflop(self, state, t0):
        p = self.p
        me = state["seat"]
        hero = [card(c) for c in state["hole_cards"]]
        board = [card(c) for c in state["board"]]
        pot, to_call = state["pot"], state["to_call"]
        folded, bets = state["folded"], state["bets"]
        live = [i for i in range(len(folded)) if not folded[i] and i != me]

        raised_pre = set()
        bettor = -1
        for h in state["history"]:
            if h["action"] == "raise":
                if h["street"] == "preflop":
                    raised_pre.add(h["seat"])
                elif h["street"] == state["street"] and h["seat"] != me:
                    bettor = h["seat"]

        widths = []
        for i in live[:3]:
            s = self._seat(i)
            if i in raised_pre:
                widths.append(max(self._rate(s.pfr, s.hands, p["prior_pfr"]), 0.08))
            else:
                widths.append(max(self._rate(s.vpip, s.hands, p["prior_vpip"]), 0.15))
        eq = self._equity(hero, board, widths, t0)

        if to_call == 0:
            if eq >= p["big_value"]:
                return self._raise(state, max(bets) + p["big_bet_frac"] * pot)
            if eq >= p["value"]:
                return self._raise(state, max(bets) + p["bet_frac"] * pot)
            if len(live) == 1 and me in raised_pre:
                s = self._seat(live[0])
                fold_rate = self._rate(s.folds, s.folds + s.continues, p["prior_fold"])
                if fold_rate >= p["bluff_fold_rate"] and self.rng.random() < p["bluff_freq"]:
                    return self._raise(state, max(bets) + p["bluff_frac"] * pot)
            return self._passive(state)

        odds = to_call / (pot + to_call)
        s = self._seat(bettor) if bettor >= 0 else Seat()
        aggr = self._rate(s.bets, s.bets + s.passive, p["prior_aggr"])
        size = min(1.0, to_call / max(pot - to_call, 1))
        need = odds + p["call_margin"] + p["passive_margin"] * (1.0 - aggr) * size
        if eq >= p["big_value"] + 0.5 * p["passive_margin"] * (1.0 - aggr):
            return self._raise(state, max(bets) + 0.75 * (pot + to_call))
        if eq >= need - p["risk"]:
            return self._call(state)
        return self._passive(state)

    def _equity(self, hero, board, widths, t0):
        """Chance of winning at showdown against one hand per width, each drawn from that top share."""
        p = self.p
        trials = p["trials"] if self.spent < p["round_budget_s"] else p["trials"] // 4
        deadline = t0 + p["decision_ms"] / 1000.0
        used = set(hero)
        used.update(board)
        deck = [c for c in DECK if c not in used]
        missing = 5 - len(board)
        need = missing + 2 * len(widths)
        sample, clock = self.rng.sample, time.perf_counter
        fixed = score(hero + board) if not missing else 0
        won = 0.0
        done = 0
        for t in range(trials):
            if not t & 7 and clock() > deadline:
                break
            draw = sample(deck, need)
            ok = True
            k = missing
            for w in widths:
                if w < 0.95 and hand_pct(draw[k], draw[k + 1]) > w:
                    ok = False
                    break
                k += 2
            if not ok:
                # Outside a seat's range: keep one deal in four so the estimate never starves.
                if t & 3:
                    continue
            full = board + draw[:missing] if missing else board
            mine = score(hero + full) if missing else fixed
            best = 0
            k = missing
            for _ in widths:
                v = score(draw[k:k + 2] + full)
                if v > best:
                    best = v
                k += 2
            won += 1.0 if mine > best else 0.5 if mine == best else 0.0
            done += 1
        return won / done if done else 0.5
