"""Hand reading shared by the opponent pool, and a bot whose behaviour is set by a stats profile.

    Agent = make_agent({"open": 0.05, "limp": 0.40})   # keys left out fall back to DEFAULT
"""
import random

RANKS = "23456789TJQKA"
# The 169 starting hands, best first: the same string as ORDER in the repo's bot.py.
ORDER = (
    "AA KK QQ JJ TT 99 AKs 88 AQs AKo AJs AQo KQs ATs KJs 77 AJo KTs QJs A9s ATo KQo 66 A8s KJo K9s "
    "A9o A7s QTs A5s JTs A4s QJo KTo Q9s A6s QTo A8o K8s K9o 55 J9s A5o Q9o JTo A7o Q8s K6s T9s A6o "
    "A3s K7s K8o A2s A4o J8s T8s K5s 44 A3o 98s T9o Q7s J9o K6o K3s Q5s A2o J7s Q8o K4s T7s K7o K5o "
    "J8o Q6s K2s Q4s 87s Q7o K4o T8o 98o 97s Q3s 33 Q2s J5s T6s J7o J6s J3s 96s Q6o Q5o T7o J4s K3o "
    "87o 86s 22 76s 97o K2o 95s 85s Q4o 75s T5s J2s T4s J6o T3s Q3o 94s 96o Q2o 65s J5o J4o T6o 76o "
    "86o 92s 53s T2s 64s J3o 84s 54s 74s 85o 93s T4o 75o T5o 95o 65o 73s J2o 82s 83s 63s 43s 54o 64o "
    "72s 42s T2o 94o 52s T3o 74o 62s 32s 93o 92o 84o 53o 63o 43o 83o 82o 73o 42o 52o 62o 72o 32o"
)

# What a seat does when nothing is known about it; also the full list of profile keys.
DEFAULT = {
    "shove": 0.02,        # share of hands it shoves preflop
    "open": 0.15,         # preflop with no raise yet: share it raises
    "limp": 0.12,         # preflop with no raise yet: share it calls
    "reraise": 0.06,      # facing a preflop raise: share it re-raises
    "call_raise": 0.15,   # facing a preflop raise: share it calls
    "bet": 0.35,          # postflop, checked to: share it bets
    "raise": 0.08,        # postflop, facing a bet: share it raises
    "fold_to_bet": 0.45,  # postflop, facing a bet: share it folds
    "open_bb": 3.0,       # usual first raise preflop, in big blinds
    "bet_pot": 0.6,       # usual postflop bet or raise, as a share of the pot
}

# Where each made-hand class sits among all hands, as a (best, worst) share; index is `made`.
# shortcut: fixed bands for a random hand, so a clone's postflop rates only roughly match its profile;
# fit the bands per seat if clones prove too far off the real bots.
BANDS = [(0.55, 1.0), (0.30, 0.55), (0.12, 0.30), (0.06, 0.12), (0.0, 0.06)]
DRAW_BAND = (0.30, 0.60)


def _build_pct():
    pct, seen = {}, 0
    for name in ORDER.split():
        seen += 6 if name[0] == name[1] else 4 if name[2] == "s" else 12
        pct[name] = seen / 1326.0
    return pct


PCT = _build_pct()


def hand_name(hole):
    """["Kd", "As"] -> "AKo"."""
    a, b = sorted(hole, key=lambda c: -RANKS.index(c[0]))
    return a[0] + b[0] + ("" if a[0] == b[0] else "s" if a[1] == b[1] else "o")


def pct(hole):
    """Share of all starting hands at least as good as this one: near 0 for aces, 1 for 32o."""
    return PCT[hand_name(hole)]


def _run(ranks, k):
    """True when the ranks hold k in a row, the ace also playing low."""
    m = 0
    for r in ranks:
        m |= 2 << r
    m |= m >> 13
    full = (1 << k) - 1
    return any(m >> i & full == full for i in range(15 - k))


def _category(cards):
    """0 high card .. 8 straight flush, for three to seven cards."""
    counts, suits = {}, {}
    for c in cards:
        r = RANKS.index(c[0])
        counts[r] = counts.get(r, 0) + 1
        suits.setdefault(c[1], []).append(r)
    flush = [rs for rs in suits.values() if len(rs) >= 5]
    n = sorted(counts.values(), reverse=True) + [0]
    if flush and _run(flush[0], 5):
        return 8
    if n[0] == 4:
        return 7
    if n[0] == 3 and n[1] >= 2:
        return 6
    if flush:
        return 5
    if _run(counts, 5):
        return 4
    if n[0] == 3:
        return 3
    if n[0] == 2:
        return 2 if n[1] == 2 else 1
    return 0


def strength(hole, board):
    """(made, draw) after the flop, counting only what the hole cards add to the board.

    made: 0 nothing, 1 a pair below top pair, 2 top pair or an overpair, 3 two pair,
    4 three of a kind or better. draw: four to a flush or to a straight with a card to come.
    """
    cards = hole + board
    ours, theirs = _category(cards), _category(board)
    h = [RANKS.index(c[0]) for c in hole]
    b = [RANKS.index(c[0]) for c in board]
    if ours > theirs and ours >= 3:
        made = 4
    elif ours == 2 and theirs == 0:
        made = 3
    elif ours > theirs:
        pair = max(r for r in h if h.count(r) == 2 or r in b)
        made = 2 if pair >= max(b) else 1
    else:
        made = 0
    draw = False
    if len(board) < 5 and ours < 4:
        suits = [c[1] for c in cards]
        draw = any(suits.count(c[1]) == 4 for c in hole) or (_run(h + b, 4) and not _run(b, 4))
    return made, draw


def passive(state):
    return {"action": "check" if "check" in state["legal_actions"] else "fold"}


def call(state):
    return {"action": "call" if "call" in state["legal_actions"] else "check"}


def raise_to(state, target):
    """Raise to the nearest legal amount, or call when raising is closed."""
    if "raise" not in state["legal_actions"]:
        return call(state)
    return {"action": "raise", "amount": max(state["min_raise_to"], min(int(target), state["max_raise_to"]))}


def make_agent(profile):
    """A bot class that plays the top share of hands matching each frequency in `profile`."""
    unknown = set(profile) - set(DEFAULT)
    if unknown:
        raise KeyError("unknown profile keys: %s" % sorted(unknown))
    p = dict(DEFAULT, **profile)

    class Agent:
        def __init__(self):
            self.rng = random.Random()

        def act(self, state):
            top = max(state["bets"])
            if state["street"] == "preflop":
                q = pct(state["hole_cards"])
                if q <= p["shove"]:
                    return {"action": "all_in"}
                if not state["raises_this_street"]:
                    if q <= p["open"]:
                        return raise_to(state, p["open_bb"] * state["big_blind"])
                    return call(state) if q <= p["open"] + p["limp"] else passive(state)
                if q <= p["reraise"]:
                    return raise_to(state, 3 * top)
                return call(state) if q <= p["reraise"] + p["call_raise"] else passive(state)
            made, draw = strength(state["hole_cards"], state["board"])
            best, worst = DRAW_BAND if draw and not made else BANDS[made]
            q = best + (worst - best) * self.rng.random()
            size = top + p["bet_pot"] * state["pot"]
            if not state["to_call"]:
                return raise_to(state, size) if q <= p["bet"] else passive(state)
            if q <= p["raise"]:
                return raise_to(state, size)
            return passive(state) if q > 1 - p["fold_to_bet"] else call(state)

    Agent.profile = p
    return Agent


Agent = make_agent({})
