"""Floorfix public-bot port for Imperial AI Pokerbots (B intake, not C tuning).

Upstream: txnujk09/fullhouse-poker-bot, bots/floorfix/bot.py
Revision: 4fe154318949aa60430682416f148733c6f0d564
Original policy thresholds and survival conservatism are retained. That source
assumed elimination poker; Imperial resets 100BB stacks every hand. Its survival
rationale is not an Imperial performance claim. Postflop Monte Carlo is cut to
a fixed 24 samples (about 0.45 ms on a laptop with seven opponents) and no
wall-clock cutoff, so seeded benchmark runs repeat. Runtime has no files,
network, external imports or expensive preflop-table generation.

Built by research/build_floorfix.py on branch research/b-public-candidates
(commit 735061f, PR #5). Source and full MIT notice follow.

MIT License

Copyright (c) 2026 Tanuj Kakumani

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

---

This project is built for the Fullhouse Hackathon engine
(https://github.com/uzlez/fullhouse-engine, (c) 2026 Fullhouse Hackathon, MIT),
which is NOT included in this repository. The engine, its reference bots, and
any organizer-provided data remain the property of the organizers and are not
redistributed here.


"""

import random

RANKS = "23456789TJQKA"
SUITS = "shdc"  # retain upstream deck order for the seeded preflop table
RANK_IDX = {r: i for i, r in enumerate(RANKS)}

class _Card(int):
    def __new__(cls, value):
        if isinstance(value, str):
            value = RANKS.index(value[0]) * 4 + SUITS.index(value[1])
        return int.__new__(cls, value)

    def __str__(self):
        return RANKS[self >> 2] + SUITS[self & 3]


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
    """Independent best-five evaluator for 5-7 distinct cards; higher wins."""
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


class _Eval7Compatibility:
    Card = _Card
    evaluate = staticmethod(_evaluate)
    _names = ("High Card", "Pair", "Two Pair", "Trips", "Straight", "Flush",
              "Full House", "Quads", "Straight Flush")

    @staticmethod
    def handtype(score):
        return _Eval7Compatibility._names[score >> 20]


eval7 = _Eval7Compatibility()
ALL_CARDS = [eval7.Card(r + s) for r in RANKS for s in SUITS]

BOT_NAME = "Fullhouse Floorfix (Imperial port)"
MAX_MC_SAMPLES = 24
T_PREMIUM = 0.66
T_STRONG = 0.585
T_PLAYABLE = 0.52
T_SPEC = 0.47

# Original seeded 900-sample/class table; pair stream seed 67890, other seed 12345.
PREFLOP_EQ = {'22': 0.5055555555555555,
 '32o': 0.3333333333333333,
 '32s': 0.3638888888888889,
 '33': 0.5416666666666666,
 '42o': 0.31444444444444447,
 '42s': 0.36,
 '43o': 0.3605555555555556,
 '43s': 0.3861111111111111,
 '44': 0.5588888888888889,
 '52o': 0.3472222222222222,
 '52s': 0.3794444444444444,
 '53o': 0.36444444444444446,
 '53s': 0.3861111111111111,
 '54o': 0.42777777777777776,
 '54s': 0.43333333333333335,
 '55': 0.5922222222222222,
 '62o': 0.33166666666666667,
 '62s': 0.3738888888888889,
 '63o': 0.37,
 '63s': 0.38,
 '64o': 0.3622222222222222,
 '64s': 0.4166666666666667,
 '65o': 0.38666666666666666,
 '65s': 0.42277777777777775,
 '66': 0.6144444444444445,
 '72o': 0.3388888888888889,
 '72s': 0.37,
 '73o': 0.36333333333333334,
 '73s': 0.4255555555555556,
 '74o': 0.3933333333333333,
 '74s': 0.41388888888888886,
 '75o': 0.40444444444444444,
 '75s': 0.4172222222222222,
 '76o': 0.41388888888888886,
 '76s': 0.4411111111111111,
 '77': 0.63,
 '82o': 0.35,
 '82s': 0.3861111111111111,
 '83o': 0.4011111111111111,
 '83s': 0.4061111111111111,
 '84o': 0.4072222222222222,
 '84s': 0.4588888888888889,
 '85o': 0.4305555555555556,
 '85s': 0.4477777777777778,
 '86o': 0.43833333333333335,
 '86s': 0.4627777777777778,
 '87o': 0.45611111111111113,
 '87s': 0.4822222222222222,
 '88': 0.7111111111111111,
 '92o': 0.3794444444444444,
 '92s': 0.4127777777777778,
 '93o': 0.4011111111111111,
 '93s': 0.4127777777777778,
 '94o': 0.4116666666666667,
 '94s': 0.44555555555555554,
 '95o': 0.43444444444444447,
 '95s': 0.43555555555555553,
 '96o': 0.4483333333333333,
 '96s': 0.4988888888888889,
 '97o': 0.46444444444444444,
 '97s': 0.4666666666666667,
 '98o': 0.5105555555555555,
 '98s': 0.48277777777777775,
 '99': 0.73,
 'A2o': 0.5638888888888889,
 'A2s': 0.5966666666666667,
 'A3o': 0.5722222222222222,
 'A3s': 0.5544444444444444,
 'A4o': 0.5555555555555556,
 'A4s': 0.5738888888888889,
 'A5o': 0.5816666666666667,
 'A5s': 0.5772222222222222,
 'A6o': 0.5588888888888889,
 'A6s': 0.6133333333333333,
 'A7o': 0.5711111111111111,
 'A7s': 0.5838888888888889,
 'A8o': 0.6094444444444445,
 'A8s': 0.6166666666666667,
 'A9o': 0.6394444444444445,
 'A9s': 0.6238888888888889,
 'AA': 0.8516666666666667,
 'AJo': 0.6605555555555556,
 'AJs': 0.6366666666666667,
 'AKo': 0.6644444444444444,
 'AKs': 0.6461111111111111,
 'AQo': 0.6255555555555555,
 'AQs': 0.6305555555555555,
 'ATo': 0.6383333333333333,
 'ATs': 0.6288888888888889,
 'J2o': 0.43722222222222223,
 'J2s': 0.4722222222222222,
 'J3o': 0.4861111111111111,
 'J3s': 0.475,
 'J4o': 0.4583333333333333,
 'J4s': 0.5177777777777778,
 'J5o': 0.495,
 'J5s': 0.49722222222222223,
 'J6o': 0.44333333333333336,
 'J6s': 0.5038888888888889,
 'J7o': 0.5022222222222222,
 'J7s': 0.5211111111111111,
 'J8o': 0.5188888888888888,
 'J8s': 0.5505555555555556,
 'J9o': 0.5316666666666666,
 'J9s': 0.5927777777777777,
 'JJ': 0.7733333333333333,
 'JTo': 0.5766666666666667,
 'JTs': 0.5666666666666667,
 'K2o': 0.5077777777777778,
 'K2s': 0.53,
 'K3o': 0.5033333333333333,
 'K3s': 0.5716666666666667,
 'K4o': 0.5455555555555556,
 'K4s': 0.5505555555555556,
 'K5o': 0.5083333333333333,
 'K5s': 0.5638888888888889,
 'K6o': 0.5527777777777778,
 'K6s': 0.5666666666666667,
 'K7o': 0.5427777777777778,
 'K7s': 0.5777777777777777,
 'K8o': 0.565,
 'K8s': 0.6005555555555555,
 'K9o': 0.5594444444444444,
 'K9s': 0.5927777777777777,
 'KJo': 0.6016666666666667,
 'KJs': 0.6194444444444445,
 'KK': 0.8327777777777777,
 'KQo': 0.5766666666666667,
 'KQs': 0.6344444444444445,
 'KTo': 0.6133333333333333,
 'KTs': 0.62,
 'Q2o': 0.48,
 'Q2s': 0.5138888888888888,
 'Q3o': 0.47888888888888886,
 'Q3s': 0.5211111111111111,
 'Q4o': 0.5116666666666667,
 'Q4s': 0.51,
 'Q5o': 0.5222222222222223,
 'Q5s': 0.5211111111111111,
 'Q6o': 0.515,
 'Q6s': 0.5211111111111111,
 'Q7o': 0.5238888888888888,
 'Q7s': 0.5405555555555556,
 'Q8o': 0.5555555555555556,
 'Q8s': 0.5194444444444445,
 'Q9o': 0.545,
 'Q9s': 0.5955555555555555,
 'QJo': 0.5866666666666667,
 'QJs': 0.6022222222222222,
 'QQ': 0.7772222222222223,
 'QTo': 0.5488888888888889,
 'QTs': 0.6044444444444445,
 'T2o': 0.42333333333333334,
 'T2s': 0.44333333333333336,
 'T3o': 0.41055555555555556,
 'T3s': 0.4677777777777778,
 'T4o': 0.41333333333333333,
 'T4s': 0.475,
 'T5o': 0.435,
 'T5s': 0.4777777777777778,
 'T6o': 0.45,
 'T6s': 0.49333333333333335,
 'T7o': 0.4777777777777778,
 'T7s': 0.5255555555555556,
 'T8o': 0.5155555555555555,
 'T8s': 0.5305555555555556,
 'T9o': 0.5011111111111111,
 'T9s': 0.5161111111111111,
 'TT': 0.77}

def _canonical_key(c1, c2):
    """Return the 169-class key, e.g. 'AKs', 'AKo', 'TT'."""
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if RANK_IDX[r1] < RANK_IDX[r2]:
        r1, r2 = r2, r1
    if r1 == r2:
        return r1 + r2
    return r1 + r2 + ("s" if s1 == s2 else "o")


def _representative_cards(key):
    """Pick concrete cards for a 169-class key."""
    if len(key) == 2:  # pair
        return [eval7.Card(key[0] + "s"), eval7.Card(key[1] + "h")]
    suited = key[2] == "s"
    if suited:
        return [eval7.Card(key[0] + "s"), eval7.Card(key[1] + "s")]
    return [eval7.Card(key[0] + "s"), eval7.Card(key[1] + "h")]








def _preflop_strength(cards):
    try:
        key = _canonical_key(cards[0], cards[1])
        return PREFLOP_EQ.get(key, 0.5)
    except Exception:
        return 0.5


def _is_premium(cards):
    """True for hands worth committing a full stack preflop: TT+, AQs+, AK.

    Heads-up-vs-random equity overrates small pairs and underrates big offsuit
    broadways, so we gate 100bb preflop stack-offs on hand *class*, not equity.
    """
    try:
        i1, i2 = RANK_IDX[cards[0][0]], RANK_IDX[cards[1][0]]
        hi, lo = max(i1, i2), min(i1, i2)
        suited = cards[0][1] == cards[1][1]
        T = RANK_IDX["T"]
        A, K, Q = RANK_IDX["A"], RANK_IDX["K"], RANK_IDX["Q"]
        if i1 == i2 and hi >= T:                 # TT, JJ, QQ, KK, AA
            return True
        if hi == A and lo == K:                  # AK suited/offsuit
            return True
        if suited and hi == A and lo == Q:       # AQs
            return True
        return False
    except Exception:
        return False


def _is_nut(cards):
    """Hands happy to commit a DEEP (>~30bb) stack preflop: QQ, KK, AA.

    AK / AQs / JJ / TT are premiums we play for value, but they are flip-ish
    against a wide shoving range, and busting deep forfeits ~375 hands of our
    large per-hand edge — worth far more than the flip's chip EV. So only true
    favourites stack off 100bb; everything else 3-bets/flats and keeps its
    stack (architecture: avoid 100bb coinflips, grind the edge).
    """
    try:
        i1, i2 = RANK_IDX[cards[0][0]], RANK_IDX[cards[1][0]]
        if i1 == i2 and i1 >= RANK_IDX["Q"]:     # QQ, KK, AA
            return True
        return False
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Monte-Carlo equity (postflop)
# --------------------------------------------------------------------------- #


def mc_equity(hole, board, n_opp, samples, rng):
    """Equity of `hole` vs `n_opp` random hands given `board`."""
    if n_opp <= 0:
        return 1.0
    used = set(str(c) for c in hole) | set(str(c) for c in board)
    deck = [c for c in ALL_CARDS if str(c) not in used]
    need_board = 5 - len(board)
    draws = 2 * n_opp + need_board
    if draws > len(deck):
        return 0.5
    sample = rng.sample
    evaluate = eval7.evaluate
    wins = 0.0
    n = 0
    for i in range(samples):
        d = sample(deck, draws)
        full_board = board + d[:need_board]
        my = evaluate(hole + full_board)
        idx = need_board
        best_opp = -1
        ties = 0
        for _ in range(n_opp):
            ev = evaluate(d[idx:idx + 2] + full_board)
            idx += 2
            if ev > best_opp:
                best_opp = ev
                ties = 1
            elif ev == best_opp:
                ties += 1
        if my > best_opp:
            wins += 1.0
        elif my == best_opp:
            wins += 1.0 / (ties + 1)
        n += 1
    return wins / n if n else 0.5


# --------------------------------------------------------------------------- #
# Made-hand classification (so we don't stack off ace-high)
# --------------------------------------------------------------------------- #

_STRONG_TYPES = {"Two Pair", "Trips", "Straight", "Flush", "Full House",
                 "Quads", "Straight Flush"}
_MONSTER_TYPES = {"Full House", "Quads", "Straight Flush"}


def _draw_flags(hole, board):
    """(flush_draw, straight_draw) — only meaningful before the river."""
    if len(board) >= 5:
        return False, False
    cards = hole + board
    suit_counts = {}
    for c in cards:
        s = str(c)[1]
        suit_counts[s] = suit_counts.get(s, 0) + 1
    fd = any(v == 4 for v in suit_counts.values())
    ranks = set(RANK_IDX[str(c)[0]] for c in cards)
    if RANK_IDX["A"] in ranks:
        ranks.add(-1)  # wheel ace
    oesd = False
    for lo in range(-1, 9):
        if all((lo + i) in ranks for i in range(4)):
            oesd = True
            break
    return fd, oesd


_RANK_ORDER = {"High Card": 0, "Pair": 1, "Two Pair": 2, "Trips": 3,
               "Straight": 4, "Flush": 5, "Full House": 6, "Quads": 7,
               "Straight Flush": 8}


def hand_features(hole, board):
    """Classify our made hand for both value-betting and stack-commitment.

    cat: betting ladder — 0 high card, 1 weak/middle pair, 2 top pair/overpair,
         3 two pair / trips / straight / flush, 4 full house+.
    commit: how willing we are to put a *large slice of stack* in —
         2 = stack-off worthy (trips+, or top two-pair on an unpaired board),
         1 = good for value but pot-control (one pair, board-assisted two pair),
         0 = showdown value only (ace-high, board pair we don't improve).

    The split matters because Monte-Carlo equity vs a *random* hand overvalues
    one-pair and board-assisted two-pair holdings against a range that has
    chosen to commit — which is exactly how a 100bb stack disappears.
    """
    evaluate = eval7.evaluate
    score = evaluate(hole + board)
    ht = eval7.handtype(score)
    mr = _RANK_ORDER.get(ht, 0)
    fd, oesd = _draw_flags(hole, board)
    hole_ranks = sorted((RANK_IDX[str(c)[0]] for c in hole), reverse=True)
    board_rlist = [RANK_IDX[str(c)[0]] for c in board]
    board_ranks = sorted(board_rlist, reverse=True)
    top_board = board_ranks[0] if board_ranks else -1
    paired_board = len(set(board_rlist)) < len(board_rlist)

    if mr >= 2:                                       # two pair or better
        cat = 4 if mr >= 6 else 3
    elif mr == 1:                                     # one pair
        if hole_ranks[0] == hole_ranks[1]:            # pocket pair
            cat = 2 if hole_ranks[0] > top_board else 1
        else:
            paired = [r for r in hole_ranks if r in board_ranks]
            if not paired:                            # board is paired; we hold kickers
                cat = 0
            elif max(paired) == top_board:            # top pair
                cat = 2
            else:                                     # middle / bottom pair
                cat = 1
    else:
        cat = 0

    # River sanity: if our hole cards can't beat the board, we have nothing.
    if len(board) >= 5 and score == evaluate(list(board)):
        cat, mr = 0, 0

    if mr >= 3:                                       # trips or better -> commit
        commit = 2
    elif mr == 2:                                     # two pair
        hole_in_board = [r for r in hole_ranks if r in board_ranks]
        both_hole = (hole_ranks[0] != hole_ranks[1] and len(set(hole_in_board)) >= 2)
        commit = 2 if (both_hole and not paired_board) else 1
    elif mr == 1:
        commit = 1 if cat == 2 else 0                 # top pair/overpair worth value
    else:
        commit = 0

    return {"cat": cat, "mr": mr, "commit": commit, "ht": ht,
            "draw": fd or oesd, "fd": fd, "oesd": oesd, "paired_board": paired_board}


# --------------------------------------------------------------------------- #
# Position (derived — no button field in the state)
# --------------------------------------------------------------------------- #


def positions(state):
    """Use the actual organizer button, preserving the source seat-distance rule."""
    n = len(state["players"])
    me, button = state["seat_to_act"], state["button"]
    sb = button if n == 2 else (button + 1) % n
    bb = (sb + 1) % n
    return n, button, sb, bb, (button - me) % n


# --------------------------------------------------------------------------- #
# Opponent model (optional — degrades gracefully without match_action_log)
# --------------------------------------------------------------------------- #


def opponent_profiles(state):
    return state["_profiles"]


def classify(p):
    if p is None or p["n"] < 8:
        return "unknown"
    if p["agg"] >= 0.55 and p["foldiness"] <= 0.15:
        return "maniac"
    if p["foldiness"] >= 0.55:
        return "nit"
    if p["call"] >= 0.55 * p["n"] and p["agg"] <= 0.12:
        return "station"
    return "reg"


def last_aggressor_id(state):
    """bot_id of the most recent raiser/bettor this hand (who we're facing)."""
    log = state.get("action_log", []) or []
    players = state.get("players", []) or []
    for a in reversed(log):
        if a.get("action") in ("raise", "all_in", "big_blind"):
            seat = a.get("seat")
            if seat is not None and 0 <= seat < len(players):
                return players[seat].get("bot_id")
    return None


# --------------------------------------------------------------------------- #
# Action helpers
# --------------------------------------------------------------------------- #


def _make_raise(to_amount, state):
    """Return a legal total raise-to, including short all-in raise ranges."""
    legal = state["legal_actions"]
    low, high = state.get("min_raise_to"), state.get("max_raise_to")
    if "raise" not in legal or low is None or high is None:
        if "call" in legal:
            return {"action": "call"}
        return _safe_fallback(state)
    return {"action": "raise", "amount": int(min(high, max(low, to_amount)))}


def _bet(frac, state):
    """Bet `frac` of the pot when first in (no outstanding bet)."""
    pot = state.get("pot", 0) or 0
    return _make_raise(round(frac * pot), state)


def _raise_to(frac, state):
    """Raise to current_bet + frac*pot when facing a bet."""
    pot = state.get("pot", 0) or 0
    cur = state.get("current_bet", 0) or 0
    return _make_raise(cur + round(frac * pot), state)


# --------------------------------------------------------------------------- #
# Strategy
# --------------------------------------------------------------------------- #


def _preflop(state, ctx):
    cards = state["your_cards"]
    hs = _preflop_strength(cards)
    can_check = state.get("can_check", False)
    to_call = state.get("amount_owed", 0) or 0
    pot = state.get("pot", 0) or 0
    n_after = ctx["players_after"]
    late = n_after <= 2
    n_live = ctx["n_live"]

    suited = len(cards[0]) > 1 and len(cards[1]) > 1 and cards[0][1] == cards[1][1]
    pair = cards[0][0] == cards[1][0]

    # Count preflop raises so far (beyond the blinds).
    log = state.get("action_log", []) or []
    n_raises = sum(1 for a in log if a.get("action") in ("raise", "all_in"))

    agg = ctx["facing_archetype"]

    if n_raises == 0:
        # Unraised pot: open-raise or take a free check.
        open_now = (
            hs >= T_STRONG
            or (hs >= T_PLAYABLE and late)
            or (hs >= T_SPEC and late and (suited or pair))
        )
        if open_now:
            size = 3.0 if not late else 2.5
            # Inflate for limpers already in the pot.
            limps = sum(1 for a in log if a.get("action") == "call")
            return _make_raise(round((size + limps) * state["big_blind"]), state)
        if can_check:
            return {"action": "check"}
        # Complete from the SB / limp behind only cheaply with playable hands.
        if to_call <= state["big_blind"] and hs >= T_SPEC and late:
            return {"action": "call"}
        return {"action": "fold"}

    # Facing a raise. Two tiers of strong hands:
    #   nut (QQ+)            -> happy to commit a deep stack: 3-bet/4-bet/call off.
    #   premium (AK/AQs/JJ/TT) -> play for value, but DON'T stack off 100bb (flip-
    #                            ish vs a wide shove; busting forfeits our edge).
    #                            3-bet/flat, then pot-control postflop.
    # The maniac bonus widens our *calling* range only, never a deep stack-off.
    eff = hs + (0.06 if agg == "maniac" else (-0.02 if agg == "nit" else 0.0))
    pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0
    facing_3bet = n_raises >= 2
    stack = state.get("your_stack", 0) or 0
    my_bet = state.get("your_bet_this_street", 0) or 0
    eff_bb = (stack + my_bet) / state["big_blind"]
    commit_frac = to_call / max(1, stack + my_bet)
    premium = _is_premium(cards)
    nut = _is_nut(cards)
    short = eff_bb <= 25                            # short: getting in is mandatory

    # A re-raise / shove costing a big slice of our stack.
    if commit_frac >= 0.30:
        if nut:
            return _raise_to(1.0, state)            # QQ+: big favourite, get it in
        if short and premium:
            return _raise_to(1.0, state)            # short stack: AK/JJ/TT must commit
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}                   # deep: don't flip 100bb with AK/JJ

    if facing_3bet:
        if nut:
            return _raise_to(1.0, state)            # 4-bet QQ+ for value
        if premium:
            return {"action": "call"}               # flat AK/AQs/JJ/TT: realize equity, pot-control
        if eff >= T_STRONG and (pair or suited) and pot_odds <= 0.40:
            return {"action": "call"}               # cheap flat, hands that play
        if can_check:
            return {"action": "check"}
        return {"action": "fold"}

    # Single raise.
    if nut or premium:
        return _raise_to(1.0, state)                # 3-bet QQ+/AK/AQs/JJ/TT for value
    if eff >= T_STRONG:
        return {"action": "call"}                   # strong: flat, don't bloat
    if eff >= T_PLAYABLE and pot_odds <= 0.33 and n_live <= 3 and (suited or pair or late):
        return {"action": "call"}
    if agg == "maniac" and eff >= T_SPEC and pot_odds <= 0.4:
        return {"action": "call"}
    if can_check:
        return {"action": "check"}
    return {"action": "fold"}


def _postflop(state, ctx):
    hole = ctx["hole"]
    board = ctx["board"]
    n_opp = ctx["n_opp"]
    can_check = state.get("can_check", False)
    to_call = state.get("amount_owed", 0) or 0
    pot = state.get("pot", 0) or 0
    my_bet = state.get("your_bet_this_street", 0) or 0
    stack = state.get("your_stack", 0) or 0
    eff_stack = stack + my_bet
    late = ctx["players_after"] <= 1
    agg = ctx["facing_archetype"]

    samples = MAX_MC_SAMPLES
    eq = mc_equity(hole, board, n_opp, samples, ctx["rng"])
    feat = hand_features(hole, board)
    cat = feat["cat"]
    commit = feat["commit"]
    draw = feat["draw"]
    flop = len(board) == 3
    turn = len(board) == 4
    # Realistic outs-based draw equity (rule of 2/4). MC-vs-random overstates a
    # draw's worth against a range that has bet/raised — it credits dominated
    # overcard/ace-high outs that don't actually win. Use this, NOT mc eq, to
    # decide whether to *continue* on a draw (we called a turn raise off ~20%
    # flush equity that mc had priced at ~40%, then bricked -> bled the stack).
    _cards_to_come = 5 - len(board)
    if feat["fd"] and feat["oesd"]:
        _outs = 15
    elif feat["fd"]:
        _outs = 9
    elif feat["oesd"]:
        _outs = 8
    else:
        _outs = 0
    de = min(0.9, _outs * (0.04 if _cards_to_come >= 2 else 0.02))

    if can_check:
        # Stack-off-worthy hands (commit>=2: trips+, top two pair on an unpaired
        # board) barrel every street for value — we can get it all in.
        if commit >= 2:
            return _bet(0.75, state)
        # Everything else (commit<=1: one pair, board-assisted two pair) is a
        # one-street hand: bet ONCE on the flop for protection / thin value, then
        # POT-CONTROL (check) the turn and river. Multi-street barrels with a
        # hand we can't stack off just build a pot we fold to a raise — that is
        # how a 3-barrelled one pair bled our whole stack into the maniac. Draws
        # may semi-bluff flop/turn. Never lead into a maniac (no fold equity).
        if agg != "maniac":
            if draw and eq >= 0.34 and n_opp <= 2 and (flop or turn):
                return _bet(0.55, state)                   # semi-bluff
            if flop:
                if cat >= 2:
                    return _bet(0.5, state)                # c-bet top pair+ / two pair once
                # cat<=1 (middle/second pair, pocket pair under an overcard) has
                # showdown value but is too vulnerable to thin-value into a built
                # pot — betting it just bloats a pot we fold (4-bet a KK, c-bet an
                # A-high flop, fold the jam -> bled 7.6k). Check it down instead.
                if cat == 0 and n_opp <= 2 and late and agg != "station":
                    if ctx["rng"].random() < 0.5:
                        return _bet(0.5, state)            # stab; give up if raised
        return {"action": "check"}

    # Facing a bet.
    pot_odds = to_call / (pot + to_call) if (pot + to_call) > 0 else 1.0
    commit_frac = to_call / max(1, eff_stack)              # share of stack this call costs
    stack_off = commit_frac >= 0.55                        # risks most of our stack
    big_bet = (not stack_off) and (commit_frac >= 0.28 or to_call >= 0.70 * pot)
    # Bettors beat a random hand -> discount MC equity, more for big bets/tight
    # opponents. Maniacs barrel air, so don't discount vs them.
    if agg == "maniac":
        disc = 0.0
    else:
        disc = 0.13 if (big_bet or stack_off) else 0.06
    eff_eq = eq - disc

    # Raise monsters for value only vs a small/medium bet (don't bloat marginal).
    if commit >= 2 and not (big_bet or stack_off) and eff_eq >= 0.60:
        return _raise_to(0.8, state)

    if stack_off:
        # Put a full stack in ONLY with a made hand we're ahead with. Not with a
        # draw, not with one pair: MC-vs-random overstates those against a range
        # that has jammed, and the format punishes 100bb coinflips. This is the
        # rule that stops us busting.
        if commit >= 2:
            return {"action": "call"}
        return {"action": "fold"}

    if big_bet:
        # A bet worth 28-55% of our stack. Continue only with a stack-off-worthy
        # hand or a draw the direct odds actually justify (realistic outs equity,
        # not mc). One pair / board-assisted two pair folds — calling these is
        # how the pot snowballs.
        if commit >= 2:
            return {"action": "call"}
        if draw and de >= pot_odds + 0.03:
            return {"action": "call"}
        return {"action": "fold"}

    # Small / normal-sized bet.
    margin = 0.02 if agg == "maniac" else 0.06
    if eff_eq >= pot_odds + margin:
        return {"action": "call"}
    # Draw: continue only if the realistic outs equity beats the price AND the
    # call doesn't commit a big slice of stack (chasing one-card draws for a
    # quarter of our stack is -EV; mc overstates them).
    if draw and de >= pot_odds and commit_frac <= 0.20:
        return {"action": "call"}
    if agg == "maniac" and cat >= 1 and eq >= pot_odds:
        return {"action": "call"}
    return {"action": "fold"}


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def _safe_fallback(state):
    if state.get("can_check", False):
        return {"action": "check"}
    return {"action": "fold"}


def decide(game_state: dict, rng) -> dict:
    try:
        if game_state.get("type") == "warmup":
            # Prime eval7 once; heavy work already done at import.
            eval7.evaluate([eval7.Card(c) for c in ("As", "Ks", "Qs", "Js", "Ts")])
            return {"action": "check"}

        cards = game_state.get("your_cards") or []
        if len(cards) < 2:
            return _safe_fallback(game_state)

        n, button, sb, bb, players_after = positions(game_state)
        players = game_state.get("players", []) or []
        me = game_state.get("seat_to_act", 0)
        n_live = sum(
            1 for p in players if not p.get("is_folded", False)
        )
        n_opp = sum(
            1
            for p in players
            if not p.get("is_folded", False) and p.get("seat") != me
        )

        profiles = opponent_profiles(game_state)
        agg_id = last_aggressor_id(game_state)
        facing_archetype = classify(profiles.get(agg_id)) if agg_id else "unknown"

        ctx = {
            "hole": [eval7.Card(c) for c in cards],
            "board": [eval7.Card(c) for c in (game_state.get("community_cards") or [])],
            "n_live": n_live,
            "n_opp": n_opp,
            "players_after": players_after,
            "facing_archetype": facing_archetype,
            "rng": rng,
        }

        street = game_state.get("street", "preflop")
        if street == "preflop" and not ctx["board"]:
            action = _preflop(game_state, ctx)
        else:
            action = _postflop(game_state, ctx)

        return action
    except Exception:
        return _safe_fallback(game_state)



def _add_history(counts, history):
    for event in history:
        action = event.get("action")
        if action not in ("raise", "all_in", "call", "fold", "check"):
            continue
        seat = event.get("seat")
        if seat is None:
            continue
        key = "seat_" + str(seat)
        p = counts.setdefault(key, {"raise": 0, "call": 0, "fold": 0, "check": 0, "n": 0})
        p["raise" if action == "all_in" else action] += 1
        p["n"] += 1


def _finish_profiles(counts):
    for p in counts.values():
        p["agg"] = p["raise"] / max(1, p["n"])
        p["foldiness"] = p["fold"] / max(1, p["raise"] + p["call"] + p["fold"])
    return counts


class Agent:
    """Imperial B candidate port; no native policy improvements or performance claim."""
    def __init__(self):
        self.on_table_start({})

    def on_table_start(self, info):
        self._rng = random.Random(0xC0FFEE + int(info.get("seat", 0)))
        self._counts = {}
        self._last_completed_hand = 0

    def on_hand_end(self, summary):
        hand = int(summary.get("hand_number", 0))
        if hand <= self._last_completed_hand:
            return
        _add_history(self._counts, summary.get("history", []))
        self._last_completed_hand = hand

    def _adapt_state(self, state):
        me = state["seat"]
        stacks, bets, folded = state["stacks"], state["bets"], state["folded"]
        history = state.get("history", [])
        # Completed hands are aggregated once, outside the decision time bank.
        # Only the current hand's short history is scanned at each decision.
        profiles = {key: dict(value) for key, value in self._counts.items()}
        if state.get("hand_number", 1) > self._last_completed_hand:
            _add_history(profiles, history)
        return {
            "your_cards": state["hole_cards"], "community_cards": state["board"],
            "street": state["street"], "seat_to_act": me, "button": state["button"],
            "players": [{"seat": i, "bot_id": "seat_" + str(i),
                         "is_folded": folded[i], "stack": stacks[i]}
                        for i in range(len(stacks))],
            "your_stack": stacks[me], "your_bet_this_street": bets[me],
            "current_bet": max(bets), "amount_owed": state["to_call"],
            "pot": state["pot"], "big_blind": state["big_blind"],
            "can_check": "check" in state["legal_actions"],
            "min_raise_to": state["min_raise_to"], "max_raise_to": state["max_raise_to"],
            "legal_actions": state["legal_actions"], "action_log": history,
            "_profiles": _finish_profiles(profiles),
        }

    def act(self, state):
        legal = state.get("legal_actions", [])
        fallback = {"action": "check" if "check" in legal else "fold"}
        try:
            action = decide(self._adapt_state(state), self._rng)
            kind = action.get("action")
            if kind == "raise":
                low, high = state.get("min_raise_to"), state.get("max_raise_to")
                if "raise" in legal and low is not None and high is not None:
                    return {"action": "raise", "amount": int(min(high, max(low, action["amount"])))}
                return {"action": "call"} if "call" in legal else fallback
            return {"action": kind} if kind in legal else fallback
        except (KeyError, TypeError, ValueError, IndexError):
            return fallback
