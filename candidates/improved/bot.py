"""Lane C bot: hand and draw analysis, with the starter strategy as a
TEMPORARY FALLBACK policy.

Status
- Done: `analyze(hole_cards, board)` (made-hand and draw assessment).
- Pending: the replacement betting strategy and preflop tables. Until those
  are agreed, `select_action` runs the starter kit's rules unchanged.

Platform contract (starter kit README): the platform imports `Agent`; a fresh
Agent is created per table per round; act(state) has 10 ms including
transport and a 10 s bank per 1,000-hand round. Standard library only.
"""
import random
from itertools import combinations

RANKS = "23456789TJQKA"
SUITS = "cdhs"
CATEGORY_NAMES = (
    "high_card", "pair", "two_pair", "three_of_a_kind", "straight",
    "flush", "full_house", "four_of_a_kind", "straight_flush",
)
ACE = 12


def card_int(card):
    """'As' -> rank_index * 4 + suit_index (same encoding as the engine)."""
    return RANKS.index(card[0]) * 4 + SUITS.index(card[1])


def card_str(c):
    return RANKS[c >> 2] + SUITS[c & 3]


# --- Straights over 13-bit rank masks (bit r = rank index r, ace = bit 12) ---

def _straight_top(mask):
    """Rank index of the highest card of the best straight in `mask`, or -1.
    The wheel A-2-3-4-5 counts, with top card 5 (index 3)."""
    for top in range(ACE, 3, -1):
        need = 0b11111 << (top - 4)
        if mask & need == need:
            return top
    if mask & 0b1111 == 0b1111 and mask >> ACE & 1:
        return 3
    return -1


STRAIGHT_TOP = tuple(_straight_top(m) for m in range(1 << 13))


# --- Made hands --------------------------------------------------------------
# Scores are tuples in the engine's format, so they compare across engines:
# (8, top) straight flush, (7, quad, kicker), (6, trips, pair),
# (5, five ranks), (4, top), (3, trips, k1, k2), (2, high, low, kicker),
# (1, pair, k1, k2, k3), (0, five ranks). Higher tuple wins.

def score_five(cards):
    ranks = sorted((c >> 2 for c in cards), reverse=True)
    flush = len({c & 3 for c in cards}) == 1
    mask = 0
    for r in ranks:
        mask |= 1 << r
    top = STRAIGHT_TOP[mask] if len(set(ranks)) == 5 else -1
    if flush and top >= 0:
        return (8, top)
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    # Group by (count, rank), biggest group first, then higher rank.
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    shape = tuple(n for _, n in groups)
    order = tuple(r for r, _ in groups)
    if shape == (4, 1):
        return (7,) + order
    if shape == (3, 2):
        return (6,) + order
    if flush:
        return (5,) + tuple(ranks)
    if top >= 0:
        return (4, top)
    if shape == (3, 1, 1):
        return (3,) + order
    if shape == (2, 2, 1):
        return (2,) + order
    if shape == (2, 1, 1, 1):
        return (1,) + order
    return (0,) + tuple(ranks)


def best_five(hole, board):
    """Best 5 of hole + board (5-7 cards). Among equal-scoring choices, takes
    the one using the fewest hole cards, so 'plays the board' is exact.
    Returns (score, five_cards, hole_cards_used)."""
    hole_set = set(hole)
    best = None
    for five in combinations(hole + board, 5):
        s = score_five(five)
        used = sum(1 for c in five if c in hole_set)
        key = (s, -used)
        if best is None or key > best[0]:
            best = (key, five)
    (score, neg_used), five = best
    return score, list(five), -neg_used


def group_category(cards):
    """Category from rank groups only, for 1-4 cards (no straight or flush
    is possible). Used for the board on the flop and turn."""
    counts = {}
    for c in cards:
        counts[c >> 2] = counts.get(c >> 2, 0) + 1
    shape = sorted(counts.values(), reverse=True)
    if shape[0] == 4:
        return 7
    if shape[0] == 3:
        return 6 if len(shape) > 1 and shape[1] >= 2 else 3
    if shape[0] == 2:
        return 2 if len(shape) > 1 and shape[1] == 2 else 1
    return 0


def _pair_classes(hole, board):
    """Pairs our hole cards make, labelled against the board's ranks."""
    board_ranks = sorted({c >> 2 for c in board}, reverse=True)
    out = []
    h1, h2 = hole[0] >> 2, hole[1] >> 2
    if h1 == h2:
        if h1 in board_ranks:
            return out  # a set, not a pair
        if h1 > board_ranks[0]:
            label = "overpair"
        elif h1 < board_ranks[-1]:
            label = "underpair"
        else:
            label = "pocket_pair_between_board_ranks"
        out.append({"type": label, "rank": RANKS[h1], "hole_cards": 2})
        return out
    for r, other in ((h1, h2), (h2, h1)):
        if r not in board_ranks:
            continue
        i = board_ranks.index(r)
        if i == 0:
            label = "top_pair"
        elif i == len(board_ranks) - 1:
            label = "bottom_pair"
        else:
            label = "middle_pair"
        out.append({"type": label, "rank": RANKS[r], "hole_cards": 1,
                    "board_rank_position": i + 1, "kicker": RANKS[other]})
    return out


def assess_hand(hole, board):
    score, five, used = best_five(hole, board)
    category = score[0]
    if len(board) == 5:
        board_score = score_five(board)
        board_category = board_score[0]
    else:
        board_score = None
        board_category = group_category(board)
    plays_board = len(board) == 5 and used == 0
    if plays_board:
        contribution = "none_plays_board"
    elif category > board_category:
        contribution = "improves_board_category"
    else:
        contribution = "kicker_only"  # same category as the board alone
    return {
        "category": category,
        "category_name": CATEGORY_NAMES[category],
        "score": score,
        "best_five": [card_str(c) for c in five],
        "hole_cards_used": used,
        "board_category": board_category,
        "board_category_name": CATEGORY_NAMES[board_category],
        "board_score": board_score,
        "hole_contribution": contribution,
        "plays_board": plays_board,
        "board_paired": len({c >> 2 for c in board}) < len(board),
        "pairs_with_hole_cards": _pair_classes(hole, board) if category in (1, 2) else [],
    }


# --- Draws -------------------------------------------------------------------

def _mask(cards):
    m = 0
    for c in cards:
        m |= 1 << (c >> 2)
    return m


def _unseen(known):
    return [c for c in range(52) if c not in known]


def _straight_kind(ranks, mask):
    """Classify direct straight-completing ranks: open_ended, double_gutshot
    or gutshot (A-2-3-4 and J-Q-K-A count as gutshots: one end is closed)."""
    if len(ranks) == 1:
        return "gutshot"
    lows = {r: ([r, -1] if r == ACE else [r]) for r in ranks}
    for a in ranks:
        for b in ranks:
            for lo in lows[a]:
                if b - lo == 5 and all(mask >> k & 1 for k in range(lo + 1, b)):
                    return "open_ended"
    return "double_gutshot"


def _probabilities(n, unseen_count, street):
    out = {"outs": n, "unseen_cards": unseen_count,
           "next_card": n / unseen_count}
    if street == "flop":
        out["by_river"] = 1 - ((47 - n) / 47) * ((46 - n) / 46)
    return out


def assess_draws(hole, board):
    """Direct, shared-board and backdoor draws on the flop and turn.

    Probabilities are the chance of hitting a fixed set of completion outs,
    NOT the chance of winning: an out can still lose (e.g. to a bigger hand
    or a board pair), and draws are only to categories we don't hold yet.
    """
    street = {3: "flop", 4: "turn"}.get(len(board))
    if street is None:
        return {"street": "river" if len(board) == 5 else "preflop", "applicable": False}
    known = set(hole) | set(board)
    unseen = _unseen(known)
    n_unseen = len(unseen)  # 47 on the flop, 46 on the turn
    all_cards = hole + board
    mask, board_mask = _mask(all_cards), _mask(board)
    direct, shared, backdoor = [], [], []

    # Flush draws: by suit.
    have_flush = False
    for s in range(4):
        h = sum(1 for c in hole if c & 3 == s)
        b = sum(1 for c in board if c & 3 == s)
        outs = [c for c in unseen if c & 3 == s]
        if h + b >= 5:
            have_flush = True
        elif h + b == 4:
            rec = {"type": "flush_draw", "suit": SUITS[s], "hole_cards_in_suit": h,
                   "out_cards": [card_str(c) for c in outs]}
            (direct if h else shared).append(rec)
        elif h + b == 3 and street == "flop":
            p = len(outs) * (len(outs) - 1) / (47 * 46)
            rec = {"type": "backdoor_flush", "suit": SUITS[s], "hole_cards_in_suit": h,
                   "needs": "turn and river both of suit", "probability_by_river": p}
            (backdoor if h else shared).append(rec)

    # Straight draws: which single ranks complete a straight we don't have.
    have_straight = STRAIGHT_TOP[mask] >= 0
    if not have_straight:
        mine, board_only = [], []
        for r in range(13):
            if mask >> r & 1:
                continue
            top_all = STRAIGHT_TOP[mask | 1 << r]
            if top_all < 0:
                continue
            # Shared if the board plus this card makes an equal or better straight.
            (board_only if STRAIGHT_TOP[board_mask | 1 << r] >= top_all else mine).append(r)
        if mine:
            outs = [c for c in unseen if (c >> 2) in mine]
            direct.append({"type": _straight_kind(mine, mask),
                           "completing_ranks": [RANKS[r] for r in mine],
                           "out_cards": [card_str(c) for c in outs]})
        if board_only:
            outs = [c for c in unseen if (c >> 2) in board_only]
            shared.append({"type": "board_straight_draw",
                           "completing_ranks": [RANKS[r] for r in board_only],
                           "out_cards": [card_str(c) for c in outs]})

        # Backdoor straights (flop): two new ranks needed, neither enough alone.
        if street == "flop":
            singles = set(mine) | set(board_only)
            copies = [4 - sum(1 for c in known if c >> 2 == r) for r in range(13)]
            routes, p = [], 0.0
            for a in range(13):
                for b in range(a + 1, 13):
                    if mask >> a & 1 or mask >> b & 1 or a in singles or b in singles:
                        continue
                    m2 = mask | 1 << a | 1 << b
                    top_all = STRAIGHT_TOP[m2]
                    if top_all < 0 or STRAIGHT_TOP[board_mask | 1 << a | 1 << b] >= top_all:
                        continue
                    routes.append(RANKS[a] + RANKS[b])
                    # Turn+river being exactly ranks {a, b}, either order.
                    p += 2 * copies[a] * copies[b] / (47 * 46)
            if routes:
                backdoor.append({"type": "backdoor_straight", "rank_pairs": routes,
                                 "probability_by_river": p})

    combined = sorted({o for d in direct for o in d["out_cards"]},
                      key=lambda s: card_int(s))
    for d in direct + shared:
        if "out_cards" in d:  # one-card draws; backdoors carry their own odds
            d.update(_probabilities(len(d["out_cards"]), n_unseen, street))
    return {
        "street": street,
        "applicable": True,
        "has_flush": have_flush,
        "has_straight": have_straight,
        "direct": direct,
        "shared_board": shared,
        "backdoor": backdoor,
        "combined_direct_outs": combined,
        "combined": _probabilities(len(combined), n_unseen, street),
        "note": "Chance of hitting a fixed set of completion outs, not of winning.",
    }


def analyze(hole_cards, board_cards):
    """Structured hand and draw assessment from our cards and public cards.

    hole_cards, board_cards: card strings as in `state` (e.g. ["As", "Kd"]).
    Preflop returns only hole-card facts; the river reports no draws.
    """
    hole = [card_int(c) for c in hole_cards]
    board = [card_int(c) for c in board_cards]
    hi, lo = sorted((hole[0] >> 2, hole[1] >> 2), reverse=True)
    result = {
        "street": {0: "preflop", 3: "flop", 4: "turn", 5: "river"}[len(board)],
        "hole": {"high": RANKS[hi], "low": RANKS[lo], "pocket_pair": hi == lo,
                 "suited": hole[0] & 3 == hole[1] & 3},
    }
    if board:
        result["hand"] = assess_hand(hole, board)
        result["draws"] = assess_draws(hole, board)
    return result


# --- Action selection --------------------------------------------------------

def select_action(state, analysis):
    """TEMPORARY FALLBACK: the starter kit's rules, unchanged. `analysis` is
    deliberately unused until the replacement strategy is agreed."""
    return _starter_fallback(state)


def _starter_fallback(state):
    legal = state["legal_actions"]
    hole = state["hole_cards"]
    ranks = sorted("23456789TJQKA".index(c[0]) for c in hole)
    strong = ranks[0] == ranks[1] or ranks[1] >= 11  # pocket pair, or K/A high

    if strong and "raise" in legal:
        target = state["min_raise_to"] + state["pot"] // 2
        return {"action": "raise", "amount": min(target, state["max_raise_to"])}
    if "check" in legal:
        return {"action": "check"}
    if state["to_call"] <= state["big_blind"] * 2 or strong:
        return {"action": "call"}
    return {"action": "fold"}


class Agent:
    def __init__(self):
        self.rng = random.Random()

    def on_table_start(self, info):
        self.seat = info["seat"]

    def act(self, state):
        try:
            analysis = analyze(state["hole_cards"], state["board"])
        except Exception:
            analysis = None  # never let analysis break a decision
        return select_action(state, analysis)

    def on_hand_end(self, summary):
        pass
