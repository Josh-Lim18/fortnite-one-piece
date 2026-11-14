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
    # Exploiting seats that do not fold: these rates use a light prior so a station shows within ~15 hands.
    "sticky_prior": 3.0,       # hands of prior behind the call-big-bet and fold-to-bet rates below
    "prior_pfcall": 0.30,      # share of big preflop raises a seat continues against
    "pf_big_bb": 3.0,          # a preflop raise to this many big blinds counts as a big bet
    "value_edge": 0.12,        # preflop: raise to the max when its edge is this share of the raise
    "allin_margin": 0.03,      # call a preflop all-in with equity this far above the pot odds
    "sticky_fold": 0.35,       # postflop fold-to-bet rate at and above which a seat gets no special treatment
    "sticky_value": 0.52,      # value-bet threshold against a seat that never folds
    "sticky_allin": 0.70,      # get it all in postflop with this equity against a seat that never folds
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

# All-in equity of each ORDER class against a random hand from the top w share of hands,
# one hex byte (equity x 255) per width in EQ_WIDTHS, 4,000 Monte Carlo deals per entry.
EQ_WIDTHS = (0.03, 0.06, 0.10, 0.15, 0.20, 0.30, 0.40, 0.55, 0.70, 0.85, 1.0)
RANGE_EQ = (
    "cdd7d9d9dad9dad7dad6d8adb2b4bbbec3c9ccced0d38f9aa7abafb7bbc0c5c9cc6e88979fa3afadb6bebec4"
    "5077889492a6a9b1b6bac0356d7a868c959ca9abb0b86c86989fa3a9a8acacabac2f5b727f7d8d959fa4acb1"
    "626987929ea5a3a8a8a6ab647b9198a0a5a6a6a4a6a55d597786909fa1a2a5a7a959617d8c969b9ea1a2a5a3"
    "5e586d7283848b99a09f9f5656687f8a96979e9fa3a7545b646876808a92979f9f32586b797a898b939aa4a7"
    "585475838e94939ea0a0a14e5c5e636c80849392999d52595d616d757a888f959a4c4e5d6d7d8c93969b9ca5"
    "4c495c77818f959b9ba0a255525e6f7c7d88919b989e30596a737a83878e939aa04c4e5a6a73858c91979b9e"
    "4f545a647274858e9396984452596068727f8a8e94984145526878868f9196999b4b50596a7381858e98999e"
    "4e525e61617374868e9495524d5e64707b808c8f9396445a58625e69757a838d8f4f4f59677378828a8d9399"
    "4450545c626d72838c909348504f6067737c8c90979a3e515559616a727f898d944e4c5b657276828a959698"
    "434f535c5c6d717c858f9347424e626b7f88919495954750575b5f6d75848a92923b4950535c6d7482879092"
    "345b6870777d85898e93993c505a595f626f787d89944649536068717c83888d9433465155545e6c7582898b"
    "3b53515657656d76818b8d4744515e667a818b8e97953d48595957616c788387904850575a60686f7b878b8f"
    "3a53595c5f636a767982884043515c687578888a8f944d515a64737b7f848d8f95474c585965687281888d91"
    "3c444d5058666d7e82868d4c4f5d676c777f878c8e954646515f6b74777e858a923c4f57595960686f778188"
    "384d585c5d63636c737f86474d575662666d76828e8c3258656b74797f83888d934444525e69707684878991"
    "3350575c5d5f656b7277832d4b51525759616a727c833f47515b555c64737f848b3249504d555d6372798089"
    "3c465053555e65727d8689424f565b616367757c8189404a5356595f636e747f8845454e5e686f757f828689"
    "3c4a535754605f6a727c84374347524d595f717d8488464e575c5f656d7680878a354b51585b5d616771797f"
    "3d474c515b5f6b798088893d464e4f5b5d63707d818731474c50525a5d69747d863e4b5256565f66707a848a"
    "424e5656616368727b81883f4b5156565a686d757f86324c57595e5e65666b737b3340464e51596169787d86"
    "3c424c4f5a59656f7b81852f444c4f54565d646e757b25445051535b5f666b6c76324b545a5b5d60656b757d"
    "3e475156585c616a747d822d59656c727a7a7c82838a3f4a4e52555e6166717c7f364c4e51575b60636f797f"
    "364e4c54555b5f656d737d3140484c4c555b67707a7e3a4c4e5657565e676f7b8138494e54535a5e656c747d"
    "2f4c5156585a5f676a7079333f4f4d4d575b6c747a823840494d52545a676e7a7e2c43484d4d555962697279"
    "364b4e5255595d636c727b3945494c565b606e7a7b852b444e5155585c5b656a73354b51595c5f5f63646f76"
    "305563686f73777c7d7e82364d575e5c636564646b742a454d4e53545a62686f783a444c4d555a616f747c82"
    "2e4b505457575b63646d7330485257585a5d5e646b6a3142474a4e565a626e767e35475357595d6160626a6f"
    "314849515155586067747732454d4f53595e626772792f4a4c5155535a5e676d772c4045484e50565c69747a"
    "30434c5150575b5f646d773542494b4f535a616d747f28464d4d535854575b666e25404a504f53555b626972"
    "303c454a4f5159616c72793a4c595b615e6267646c6e2f42464a494f575e6472782e3d464a4a4f545a636e77"
    "283d464b4e4f545a646a782d444c5055585d605f666a2a414c4d5158595e5c666f27474c4f4f545a5b60636b"
    "364a52555a5d5d625f616631454a504e55595d666b72334b54565a5d5c5f5f666d2c3c44494b4e5358626a76"
    "2c48535555575b5e60676c384f555a5e5c606461636932495155565859605c63692740444c4d5052575b616b"
    "2a464c4f5456555a61646c253d4346494d52565e646e2b414a514e56585b575f67283f414945505358606970"
    "223f47484a4f52555b636f2e41475052595a575960692e4249505255585a625d642c3c4449484b5358616a71"
    "2842484e51545a575a61652945495352545a585d5c6832494e545a59575c5f5f65334a5558585c5d5d625f5f"
    "3245504d525556585a5e632c424c4e52505955575f63243d494d4e545256595d5f30424e5351585856585c5f"
    "253b4146484f50575c636d1e3644454a4b4d505a5e6a31464c535658575c5c5f60243c41464a504e535c626f"
    "263e454a4e525353575c5e2f444a4e52535756585d602f464e5154565653595e5d1e3b4343494d504f575c67"
    "203a4347474c4d4e565c64233a4448494e4f505761662a41484d5152535556575d263e444b4e505150545a5c"
    "2a42494c4d4f545552565a203640434849495051565d1f354445484d4c4c4e575c213643454851524e515b5d"
    "273c46494a515052545556283c44484d4f4d51555556233d3e4448494e4f4c52541e37413f464b494c4e525b"
    "243943494c4c4c4d4e5050"
)


def _build_pct():
    """PCT[key] = share of all starting hands at least this good; CLS[key] = ORDER index; key = hi * 26 + lo * 2 + suited."""
    pct = [1.0] * (13 * 26)
    cls = [0] * (13 * 26)
    seen = 0
    for k, name in enumerate(ORDER.split()):
        hi, lo = RANKS.index(name[0]), RANKS.index(name[1])
        seen += 6 if hi == lo else 4 if name[2] == "s" else 12
        suited = 1 if name[-1] == "s" else 0
        pct[hi * 26 + lo * 2 + suited] = pct[lo * 26 + hi * 2 + suited] = seen / 1326.0
        cls[hi * 26 + lo * 2 + suited] = cls[lo * 26 + hi * 2 + suited] = k
    return pct, cls


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


PCT, CLS = _build_pct()
STRAIGHT, TOP5 = _build_masks()
DECK = list(range(52))
_EQ_N = len(EQ_WIDTHS)
EQ = [[int(RANGE_EQ[(i * _EQ_N + j) * 2:(i * _EQ_N + j) * 2 + 2], 16) / 255.0 for j in range(_EQ_N)]
      for i in range(169)]


def card(text):
    return RANKS.index(text[0]) * 4 + SUITS.index(text[1])


def hand_pct(c1, c2):
    return PCT[(c1 >> 2) * 26 + (c2 >> 2) * 2 + (1 if (c1 & 3) == (c2 & 3) else 0)]


def hand_cls(c1, c2):
    return CLS[(c1 >> 2) * 26 + (c2 >> 2) * 2 + (1 if (c1 & 3) == (c2 & 3) else 0)]


def range_equity(i, width):
    """All-in equity of ORDER class i against the top `width` share of hands, interpolated between table widths."""
    row = EQ[i]
    if width <= EQ_WIDTHS[0]:
        return row[0]
    for j in range(1, _EQ_N):
        if width <= EQ_WIDTHS[j]:
            lo = EQ_WIDTHS[j - 1]
            f = (width - lo) / (EQ_WIDTHS[j] - lo)
            return row[j - 1] + f * (row[j] - row[j - 1])
    return row[-1]


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

    __slots__ = ("hands", "vpip", "pfr", "shove", "bets", "passive", "folds", "continues",
                 "pf_faced", "pf_called")

    def __init__(self):
        self.hands = self.vpip = self.pfr = self.shove = 0
        self.bets = self.passive = self.folds = self.continues = 0
        self.pf_faced = self.pf_called = 0


class Agent:
    def __init__(self, params=None):
        self.p = dict(PARAMS, **(params or {}))
        self.rng = random.Random()
        self.seats = []
        self.stack = 2000
        self.bb = 20
        self.spent = 0.0
        gc.disable()  # a collection pause can blow the 10 ms limit

    def on_table_start(self, info):
        self.seats = [Seat() for _ in range(info["num_players"])]
        self.stack = info["starting_stack"]
        self.bb = info.get("big_blind", 20)

    # ------------------------------------------------------------ profiling
    def _rate(self, count, total, prior, k=None):
        k = self.p["prior_hands"] if k is None else k
        return (count + prior * k) / (total + k)

    def _pf_call(self, s):
        return self._rate(s.pf_called, s.pf_faced, self.p["prior_pfcall"], self.p["sticky_prior"])

    def _fold_fast(self, s):
        return self._rate(s.folds, s.folds + s.continues, self.p["prior_fold"], self.p["sticky_prior"])

    def _sticky(self, s):
        """0 for a seat that folds to bets normally, 1 for one that never folds."""
        return max(0.0, 1.0 - self._fold_fast(s) / self.p["sticky_fold"])

    def _seat(self, i):
        while len(self.seats) <= i:
            self.seats.append(Seat())
        return self.seats[i]

    def on_hand_end(self, summary):
        big = self.p["big_bet"] * self.stack
        entered, raised, shoved = set(), set(), set()
        street, bet_open = "preflop", False
        pf_big = self.p["pf_big_bb"] * self.bb
        put, top = {}, 0
        for h in summary["history"]:
            a, i = h["action"], h["seat"]
            if h["street"] != street:
                street, bet_open = h["street"], False
            if a in ("small_blind", "big_blind"):
                put[i] = h["amount"]
                top = max(top, h["amount"])
                continue
            s = self._seat(i)
            if street == "preflop":
                if top >= pf_big and put.get(i, 0) < top:
                    s.pf_faced += 1
                    s.pf_called += a != "fold"
                if a == "raise":
                    put[i] = top = max(top, h["amount"])
                elif a == "call":
                    put[i] = put.get(i, 0) + h["amount"]
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
        raised, entered = set(), set()
        for h in state["history"]:
            if h["action"] == "raise":
                raises += 1
                raiser = h["seat"]
                callers_of_raise = 0
                raised.add(h["seat"])
            elif h["action"] == "call":
                entered.add(h["seat"])
                if raises:
                    callers_of_raise += 1
                else:
                    limpers += 1

        cls = hand_cls(c1, c2)
        committed = raises and (top_bet >= p["big_bet"] * self.stack or to_call >= 0.3 * self.stack)
        if committed:
            # Equity against the raiser's estimated range (and each caller holding the same) against the pot odds.
            eq = range_equity(cls, self._raise_width(raiser, raises, top_bet)) ** (1 + callers_of_raise)
            if eq >= to_call / (state["pot"] + to_call) + p["allin_margin"] - p["risk"]:
                return {"action": "all_in"}
            return self._passive(state)
        if "raise" in state["legal_actions"] and self._value_edge(state, cls, raised, entered) >= p["value_edge"]:
            return {"action": "raise", "amount": state["max_raise_to"]}

        if raises == 0:
            behind = (state["button"] - me) % n
            behind = 1 if behind == n - 1 else 0 if behind == n - 2 else behind + 2
            limit = p["iso_raise"] if behind == 0 else p["open"].get(behind, 0.12)
            if pct <= limit:
                return self._raise(state, (p["open_bb"] + limpers) * bb)
            return self._passive(state)

        width = self._raise_width(raiser, raises, top_bet)
        depth = pct / width  # 0 = top of the raiser's range, 1 = its bottom
        crowd = 0.7 ** callers_of_raise  # callers behind a raise hold real hands too
        if depth <= p["threebet_r"] * crowd:
            return self._raise(state, top_bet * 3 + to_call * callers_of_raise)
        cheap = to_call <= p["setmine_cost"] * self.stack
        if cheap and (c1 >> 2) == (c2 >> 2):
            return self._call(state)
        if to_call <= 0.08 * self.stack and pct <= min(p["call_r"] * width, p["call_cap"]):
            return self._call(state)
        return self._passive(state)

    def _raise_width(self, raiser, raises, top_bet):
        """Share of hands the last preflop raiser holds, from how often it raises and shoves."""
        p = self.p
        opp = self._seat(raiser)
        pfr = self._rate(opp.pfr, opp.hands, p["prior_pfr"])
        shove = self._rate(opp.shove, opp.hands, p["prior_shove"])
        if top_bet >= p["big_bet"] * self.stack:
            width = shove
        elif raises >= 2:
            width = max(pfr * 0.3, shove)
        else:
            width = pfr
        return max(width, 0.02)

    def _value_edge(self, state, cls, raised, entered):
        """Expected gain of raising to the max, per chip raised, if it is called: each live seat calls at its
        call-big-bet rate with that top share of what it holds; multiway equity is the product of heads-up ones."""
        p = self.p
        me = state["seat"]
        dp, q = [1.0], [1.0]  # by number of callers: sum of P(callers) * equity, and P(callers)
        for i, f in enumerate(state["folded"]):
            if f or i == me:
                continue
            s = self._seat(i)
            c = self._pf_call(s)
            if i in raised:
                held = self._rate(s.pfr, s.hands, p["prior_pfr"])
            elif i in entered:
                held = self._rate(s.vpip, s.hands, p["prior_vpip"])
            else:
                held = 1.0
            e = range_equity(cls, max(0.02, c * held))
            ndp, nq = [0.0] * (len(dp) + 1), [0.0] * (len(q) + 1)
            for k in range(len(dp)):
                ndp[k] += dp[k] * (1.0 - c)
                ndp[k + 1] += dp[k] * c * e
                nq[k] += q[k] * (1.0 - c)
                nq[k + 1] += q[k] * c
            dp, q = ndp, nq
        return sum(dp[k] * (k + 1) for k in range(1, len(dp))) - (1.0 - q[0])

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
