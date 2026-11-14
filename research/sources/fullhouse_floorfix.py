"""
Fullhouse Hackathon bot — equity-based TAG core with light exploitation.

Design (see architecture.md):
  - Preflop: O(1) lookup into a 169-hand heads-up equity table built once at
    import via eval7 Monte Carlo. Range/sizing decisions by position + action.
  - Postflop: bounded eval7 Monte-Carlo equity vs the number of live opponents,
    combined with pot odds, position, and a light opponent model.
  - Opponent model: per-bot VPIP / preflop-raise / postflop-aggression /
    fold tendency derived from match_action_log (optional) -> archetype, used to
    (a) never bluff non-folders, (b) value-bet stations bigger, (c) steal vs nits,
    (d) call down lighter vs maniacs.
  - Hard internal time budget << 2s; every path is exception-safe (a crash or
    timeout auto-folds and costs chips, so decide() must never raise).

No file writes, no network, no threads — single-threaded, stdlib + eval7 only.
"""

import os
import random
from time import perf_counter

import eval7

BOT_NAME = "Equilibrium"

# --------------------------------------------------------------------------- #
# Constants / time budget
# --------------------------------------------------------------------------- #

RANKS = "23456789TJQKA"
SUITS = "shdc"
RANK_IDX = {r: i for i, r in enumerate(RANKS)}
ALL_CARDS = [eval7.Card(r + s) for r in RANKS for s in SUITS]

# Dedicated RNG for gameplay Monte-Carlo and mixed strategies. Seeded once so
# matches are reproducible and we never depend on global RNG state.
_RNG = random.Random(0xC0FFEE)

BIG_BLIND = 100  # engine constant (informational; we read sizes from state)

# Wall-clock budget per decision. The runner's timeout is 2s but cannot kill a
# running thread, so we stay well under it. Local timing is optimistic vs the
# 0.5-CPU container, hence the conservative cap.
SOFT_BUDGET = 0.45   # seconds of MC work
HARD_BUDGET = 0.90   # absolute ceiling before we bail to a safe action

# Preflop heads-up-equity tiers (calibrated against the table built below).
T_PREMIUM = 0.66
T_STRONG = 0.585
T_PLAYABLE = 0.52
T_SPEC = 0.47

# --------------------------------------------------------------------------- #
# Preflop equity table (built once at import — untimed by the 2s budget)
# --------------------------------------------------------------------------- #


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


def _build_preflop_table(samples=900):
    """Heads-up equity of each 169 class vs one random hand, via MC.

    Uses a private seeded RNG so the table is deterministic and does not disturb
    the global RNG used for gameplay Monte Carlo.
    """
    rng = random.Random(12345)
    table = {}
    seen = set()
    for r1 in RANKS:
        for r2 in RANKS:
            for suited in (True, False):
                if r1 == r2 and not suited:
                    continue  # pairs only once
                c1 = eval7.Card(r1 + "s")
                c2 = eval7.Card(r2 + ("s" if suited else "h"))
                if str(c1) == str(c2):
                    continue
                key = _canonical_key(str(c1), str(c2))
                if key in seen:
                    continue
                seen.add(key)
                hole = [c1, c2]
                used = {str(c1), str(c2)}
                deck = [c for c in ALL_CARDS if str(c) not in used]
                wins = 0.0
                for _ in range(samples):
                    draw = rng.sample(deck, 7)  # 2 opp + 5 board
                    board = draw[2:]
                    my = eval7.evaluate(hole + board)
                    opp = eval7.evaluate(draw[:2] + board)
                    if my > opp:
                        wins += 1.0
                    elif my == opp:
                        wins += 0.5
                table[key] = wins / samples
    # PAIR-EQUITY BUGFIX (floorfix only; the byte-locked floor lacks this): the
    # loop above DROPS all 13 pocket pairs -- the suited pass builds a duplicate
    # card (e.g. As,As) caught by the dup-guard, and the offsuit pass is skipped
    # by "pairs only once". So PREFLOP_EQ had 156/169 entries and every pair fell
    # back to hs=0.5 at runtime, which makes the bot FOLD AA/KK/QQ when opening
    # UTG/MP and never set-mine. Non-pair entries above are byte-identical to the
    # floor (same rng=12345 draws, untouched loop); pairs are computed in this
    # separate pass with an INDEPENDENT rng so they do not perturb that stream.
    prng = random.Random(67890)
    for r in RANKS:
        key = r + r
        if key in seen:
            continue
        seen.add(key)
        hole = [eval7.Card(r + "s"), eval7.Card(r + "h")]
        used = {str(hole[0]), str(hole[1])}
        deck = [c for c in ALL_CARDS if str(c) not in used]
        wins = 0.0
        for _ in range(samples):
            draw = prng.sample(deck, 7)
            board = draw[2:]
            my = eval7.evaluate(hole + board)
            opp = eval7.evaluate(draw[:2] + board)
            if my > opp:
                wins += 1.0
            elif my == opp:
                wins += 0.5
        table[key] = wins / samples
    return table


try:
    PREFLOP_EQ = _build_preflop_table()
except Exception:
    PREFLOP_EQ = {}


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


def mc_equity(hole, board, n_opp, samples, deadline):
    """Equity of `hole` vs `n_opp` random hands given `board`, capped by time."""
    if n_opp <= 0:
        return 1.0
    used = set(str(c) for c in hole) | set(str(c) for c in board)
    deck = [c for c in ALL_CARDS if str(c) not in used]
    need_board = 5 - len(board)
    draws = 2 * n_opp + need_board
    if draws > len(deck):
        return 0.5
    sample = _RNG.sample
    evaluate = eval7.evaluate
    wins = 0.0
    n = 0
    for i in range(samples):
        if (i & 31) == 0 and perf_counter() > deadline:
            break
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
    """Return (n_players, button_seat, sb_seat, bb_seat, players_after_me).

    players_after_me: how many seats act after us postflop (0 = button = best).
    """
    players = state.get("players", []) or []
    n = len(players)
    log = state.get("action_log", []) or []
    sb_seat = bb_seat = None
    for a in log:
        if a.get("action") == "small_blind" and sb_seat is None:
            sb_seat = a.get("seat")
        elif a.get("action") == "big_blind" and bb_seat is None:
            bb_seat = a.get("seat")
    me = state.get("seat_to_act", 0)
    if n <= 1:
        return n, me, sb_seat, bb_seat, 0
    if bb_seat is None:
        # Fallback: assume standard layout if blinds not visible.
        button = (me - 1) % n
    elif n == 2:
        button = sb_seat if sb_seat is not None else (bb_seat - 1) % n
    else:
        button = (sb_seat - 1) % n if sb_seat is not None else (bb_seat - 2) % n
    players_after = (button - me) % n
    return n, button, sb_seat, bb_seat, players_after


# --------------------------------------------------------------------------- #
# Opponent model (optional — degrades gracefully without match_action_log)
# --------------------------------------------------------------------------- #


def opponent_profiles(state):
    """Build per-bot tendency stats from match_action_log.

    Returns {bot_id: {"raise": r, "call": c, "fold": f, "n": total,
                       "agg": raise_freq, "foldiness": fold_freq}}.
    """
    log = state.get("match_action_log", []) or []
    prof = {}
    for e in log:
        bid = e.get("bot_id")
        act = e.get("action")
        if bid is None or act in (None, "small_blind", "big_blind"):
            continue
        p = prof.setdefault(bid, {"raise": 0, "call": 0, "fold": 0, "check": 0, "n": 0})
        if act in ("raise", "all_in"):
            p["raise"] += 1
        elif act == "call":
            p["call"] += 1
        elif act == "fold":
            p["fold"] += 1
        elif act == "check":
            p["check"] += 1
        p["n"] += 1
    for p in prof.values():
        n = max(1, p["n"])
        faced = p["raise"] + p["call"] + p["fold"]  # decisions facing a price
        p["agg"] = p["raise"] / n
        p["foldiness"] = p["fold"] / max(1, faced)
    return prof


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
    """Clamp a desired total bet to [min_raise_to, all_in] and pick the action."""
    my_bet = state.get("your_bet_this_street", 0) or 0
    stack = state.get("your_stack", 0) or 0
    max_to = stack + my_bet
    min_to = state.get("min_raise_to", my_bet + BIG_BLIND) or (my_bet + BIG_BLIND)
    to = int(max(min_to, min(to_amount, max_to)))
    if to >= max_to:
        return {"action": "all_in"}
    return {"action": "raise", "amount": to}


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
            return _make_raise(round((size + limps) * BIG_BLIND), state)
        if can_check:
            return {"action": "check"}
        # Complete from the SB / limp behind only cheaply with playable hands.
        if to_call <= BIG_BLIND and hs >= T_SPEC and late:
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
    eff_bb = (stack + my_bet) / BIG_BLIND
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

    samples = max(180, int(2400 / (n_opp + 1)))
    eq = mc_equity(hole, board, n_opp, samples, ctx["deadline"])
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
                    if _RNG.random() < 0.5:
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


def decide(game_state: dict) -> dict:
    t0 = perf_counter()
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
            "deadline": t0 + SOFT_BUDGET,
        }

        street = game_state.get("street", "preflop")
        if street == "preflop" and not ctx["board"]:
            action = _preflop(game_state, ctx)
        else:
            action = _postflop(game_state, ctx)

        # Absolute safety: if we somehow blew the budget, return something legal.
        if perf_counter() - t0 > HARD_BUDGET:
            return action if isinstance(action, dict) else _safe_fallback(game_state)
        return action
    except Exception:
        return _safe_fallback(game_state)

