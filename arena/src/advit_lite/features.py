"""advitrocks9's 51-feature state encoding, ported from numpy to plain Python.

Input: a Fullhouse-format game_state dict (chips in Fullhouse units: 100-chip big blind).
Output: (features, legal) where features is a list of 51 floats and legal a list of 5 bools,
identical to bot/features.py:encode_state_dict in the original.
"""

from advit_lite.hand_eval import evaluate

FEATURE_DIM = 51
N_ACTIONS = 5
STARTING_STACK = 10_000
BIG_BLIND = 100
LEGAL_MASK_OFFSET = 46
MAX_EVAL7_SCORE = 135004160.0
_RANKS = "23456789TJQKA"
_SUITS = "cdhs"


def card_index(card):
    """'As' -> suit * 13 + rank, suits in 'cdhs' order (the original's layout)."""
    return _SUITS.index(card[1]) * 13 + _RANKS.index(card[0])


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def infer_dealer(state, n_players=None):
    if n_players is None:
        n_players = len(state.get("players", [])) or 2
    n_players = max(int(n_players), 2)
    if state.get("dealer") is not None:
        return int(state["dealer"]) % n_players
    small_blind = big_blind = None
    for entry in state.get("action_log") or []:
        action = entry.get("action")
        if action == "small_blind" and entry.get("seat") is not None:
            small_blind = int(entry["seat"])
        elif action == "big_blind" and entry.get("seat") is not None:
            big_blind = int(entry["seat"])
        if small_blind is not None and big_blind is not None:
            break
    if small_blind is not None:
        return small_blind % n_players if n_players == 2 else (small_blind - 1) % n_players
    if big_blind is not None:
        return (big_blind - 1) % n_players if n_players == 2 else (big_blind - 2) % n_players
    return 0


def _street_index(street_name):
    return {"preflop": 0, "flop": 1, "turn": 2, "river": 3}.get(street_name, 0)


def _street_action_segment(log):
    for i in range(len(log) - 1, -1, -1):
        if log[i].get("action") == "deal":
            return log[i + 1:]
    return log


def _replay_betting_rounds(log, players, current_street_name):
    target_street = _street_index(current_street_name)
    seats = {int(p.get("seat", idx)) for idx, p in enumerate(players)}
    if not seats:
        seats = {int(e["seat"]) for e in log if e.get("seat") is not None}
    st = {"street": 0, "current_bet": 0, "last_full_raise": BIG_BLIND, "street_bets": {}, "pending": set(seats)}
    invested = {}
    folded = set()
    all_in = set()
    current_segment = []
    current_n_raises = 0
    current_last_raiser = None

    def active_seats():
        return {seat for seat in seats if seat not in folded and seat not in all_in}

    def advance_street():
        st["street"] = min(st["street"] + 1, 3)
        st["current_bet"] = 0
        st["last_full_raise"] = BIG_BLIND
        st["street_bets"] = {}
        st["pending"] = active_seats()

    for entry in log:
        action = entry.get("action")
        if action == "deal":
            advance_street()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        seats.add(seat)
        amount = max(_safe_int(entry.get("amount", 0)), 0)
        if action not in ("small_blind", "big_blind") and not st["pending"] and st["street"] < target_street:
            advance_street()
        if st["street"] == target_street:
            current_segment.append(entry)
        bets = st["street_bets"]
        if action in ("small_blind", "big_blind"):
            inc = amount
            bets[seat] = bets.get(seat, 0) + inc
            st["current_bet"] = max(st["current_bet"], bets[seat])
        elif action == "fold":
            inc = 0
            folded.add(seat)
            st["pending"].discard(seat)
        elif action == "check":
            inc = 0
            st["pending"].discard(seat)
        elif action == "call":
            inc = amount
            bets[seat] = bets.get(seat, 0) + inc
            st["pending"].discard(seat)
        elif action in ("raise", "all_in"):
            prev_bet = st["current_bet"]
            prev_seat_bet = bets.get(seat, 0)
            inc = max(0, amount - prev_seat_bet)
            bets[seat] = max(prev_seat_bet, amount)
            st["current_bet"] = max(st["current_bet"], bets[seat])
            st["pending"].discard(seat)
            if action == "all_in":
                all_in.add(seat)
            raise_size = max(0, st["current_bet"] - prev_bet)
            if raise_size > 0 and raise_size >= st["last_full_raise"]:
                st["last_full_raise"] = raise_size
                st["pending"] = {s for s in active_seats() if s != seat}
                if st["street"] == target_street:
                    current_n_raises += 1
                    current_last_raiser = seat
        else:
            inc = 0
            st["pending"].discard(seat)
        if inc:
            invested[seat] = invested.get(seat, 0) + inc

    if target_street == 0 and st["current_bet"] <= BIG_BLIND:
        current_n_raises = 0
        current_last_raiser = None
    return current_segment, invested, min(current_n_raises, 4), current_last_raiser, st["last_full_raise"]


def current_street_aggression(log, players, current_bet, street_name):
    """(n_raises, last_raiser, last_full_raise) for the current street."""
    blind_only = street_name == "preflop" and current_bet <= 100
    if current_bet <= 0 or blind_only:
        return 0, None, BIG_BLIND
    if any(entry.get("action") == "deal" for entry in log):
        n_raises = 0
        last_raiser = None
        street_current_bet = 0
        last_full_raise = BIG_BLIND
        for entry in _street_action_segment(log):
            action = entry.get("action")
            if entry.get("seat") is None:
                continue
            seat = int(entry["seat"])
            amount = _safe_int(entry.get("amount", 0))
            if action in ("small_blind", "big_blind", "call"):
                street_current_bet = max(street_current_bet, amount)
                continue
            if action not in ("raise", "all_in"):
                continue
            raise_size = max(0, amount - street_current_bet)
            street_current_bet = max(street_current_bet, amount)
            if raise_size >= last_full_raise:
                last_full_raise = raise_size
                n_raises += 1
                last_raiser = seat
        if n_raises:
            return min(n_raises, 4), last_raiser, last_full_raise
        return 1, None, BIG_BLIND
    _, _, n_raises, last_raiser, last_full_raise = _replay_betting_rounds(log, players, street_name)
    if n_raises:
        return n_raises, last_raiser, last_full_raise
    return 1, None, BIG_BLIND


def _hand_invested_from_log(log, players, street_name):
    if players is not None and not any(entry.get("action") == "deal" for entry in log):
        return _replay_betting_rounds(log, players, street_name)[1]
    invested = {}
    street_bets = {}
    for entry in log:
        action = entry.get("action")
        if action == "deal":
            street_bets.clear()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        amount = max(_safe_int(entry.get("amount", 0)), 0)
        if action in ("small_blind", "big_blind", "call"):
            inc = amount
            street_bets[seat] = street_bets.get(seat, 0) + inc
        elif action in ("raise", "all_in"):
            inc = max(0, amount - street_bets.get(seat, 0))
            street_bets[seat] = max(street_bets.get(seat, 0), amount)
        else:
            inc = 0
        if inc:
            invested[seat] = invested.get(seat, 0) + inc
    return invested


def _count_straight_out_ranks(rank_present):
    out_ranks = set()
    for start in range(9):
        missing = [r for r in range(start, start + 5) if not rank_present[r]]
        if len(missing) == 1:
            out_ranks.update(missing)
    wheel = [12, 0, 1, 2, 3]
    if sum(1 for r in wheel if rank_present[r]) == 4:
        out_ranks.update(r for r in wheel if not rank_present[r])
    return len(out_ranks)


def _detect_draws(hole, board, street):
    if street >= 3 or not board:
        return False, False, False, 0, False
    all_cards = hole + board
    suit_counts = [0, 0, 0, 0]
    for c in all_cards:
        suit_counts[c // 13] += 1
    max_suit_count = max(suit_counts)
    flush_draw = max_suit_count == 4
    flush_suit = suit_counts.index(max_suit_count) if flush_draw else -1
    nut_flush_draw = False
    if flush_draw:
        on_board = [c % 13 for c in board if c // 13 == flush_suit]
        in_hand = [c % 13 for c in hole if c // 13 == flush_suit]
        if in_hand:
            nut_flush_draw = max(in_hand) == max(on_board + in_hand)
    rank_present = [False] * 13
    for c in all_cards:
        rank_present[c % 13] = True
    outs_ranks = _count_straight_out_ranks(rank_present)
    overlap = min(outs_ranks, 2) if flush_draw and outs_ranks > 0 else 0
    draw_outs = (9 if flush_draw else 0) + outs_ranks * 4 - overlap
    return flush_draw, outs_ranks >= 2, outs_ranks == 1, draw_outs, nut_flush_draw


def _board_texture(board):
    if not board:
        return False, False, 0.0, False
    ranks = [c % 13 for c in board]
    suits = [c // 13 for c in board]
    paired = len(set(ranks)) < len(ranks)
    monotone = len(set(suits)) == 1
    n = len(ranks)
    if n < 2:
        wet = 0.0
    else:
        close = total = 0
        for i in range(n):
            for j in range(i + 1, n):
                total += 1
                if abs(ranks[i] - ranks[j]) <= 2:
                    close += 1
        wet = close / total
    rank_present = [False] * 13
    for r in ranks:
        rank_present[r] = True
    straight_possible = any(sum(1 for r in range(s, s + 5) if rank_present[r]) >= 3 for s in range(9))
    if not straight_possible:
        straight_possible = sum(1 for r in (12, 0, 1, 2, 3) if rank_present[r]) >= 3
    return paired, monotone, wet, straight_possible


def compute_legal_mask(state, n_raises=0, last_full_raise=BIG_BLIND):
    legal = [False] * N_ACTIONS
    owed = state.get("amount_owed", 0)
    stack = state.get("your_stack", 0)
    pot = state.get("pot", 0)
    min_raise = state.get("min_raise_to", 0)
    players = state.get("players", [])
    my_seat = state.get("seat_to_act", 0)
    last_full_raise = max(_safe_int(last_full_raise, BIG_BLIND), BIG_BLIND)
    if owed > 0:
        legal[0] = True
    legal[1] = True
    if stack > owed and min_raise > 0:
        pot_after_call = pot + owed
        bet_room = stack - owed
        bet_50 = round(0.50 * pot_after_call)
        if bet_50 >= last_full_raise and bet_room > bet_50:
            legal[2] = True
        if pot_after_call >= last_full_raise and bet_room > pot_after_call:
            legal[3] = True
        opp = [p.get("stack", 0) for p in players if p.get("seat") != my_seat and not p.get("is_folded")]
        max_opp = max(opp) if opp else 0
        eff_stack = min(stack, max_opp) if max_opp > 0 else stack
        if eff_stack / max(pot, 1) < 4:
            legal[4] = True
    return legal


def encode_state(state, preflop):
    """preflop = (paired[13], suited[13][13], offsuit[13][13]) equity tables."""
    paired_eq, suited_eq, offsuit_eq = preflop
    f = [0.0] * FEATURE_DIM
    my_cards = state["your_cards"]
    community = state.get("community_cards", [])
    players = state.get("players", [])
    my_seat = state["seat_to_act"]
    n_players = len(players)
    dealer = infer_dealer(state, n_players)
    street_name = state.get("street", "preflop")
    street = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}[street_name]
    pot = state.get("pot", 0)
    my_stack = state.get("your_stack", STARTING_STACK)
    to_call = state.get("amount_owed", 0)
    current_bet = state.get("current_bet", 0)

    c0, c1 = card_index(my_cards[0]), card_index(my_cards[1])
    r0, r1, s0, s1 = c0 % 13, c1 % 13, c0 // 13, c1 // 13
    hi, lo = max(r0, r1), min(r0, r1)
    board = [card_index(c) for c in community]

    f[0] = paired_eq[r0] if r0 == r1 else (suited_eq[hi][lo] if s0 == s1 else offsuit_eq[hi][lo])
    if street > 0 and community:
        f[1] = evaluate([c0, c1] + board) / MAX_EVAL7_SCORE
    fd, oesd, gs, outs, nfd = _detect_draws([c0, c1], board, street)
    f[2], f[3], f[4], f[5], f[6] = float(fd), float(oesd), float(gs), outs / 20.0, float(nfd)
    f[7], f[8] = hi / 12.0, lo / 12.0
    f[9], f[10] = float(s0 == s1), float(r0 == r1)
    f[11] = (hi - lo - 1) / 12.0 if hi != lo else 0.0
    if board:
        bp, bm, bw, sp = _board_texture(board)
        f[12], f[13] = float(bp), float(bm)
        f[14] = sum(1 for b in board if b % 13 > hi) / 5.0
        f[15], f[16] = bw, float(sp)

    f[17 + street] = 1.0
    f[21 + min((my_seat - dealer) % max(n_players, 2), 5)] = 1.0
    f[27] = pot / STARTING_STACK
    f[28] = my_stack / STARTING_STACK
    active_stacks = [p.get("stack", 0) for p in players if not p.get("is_folded")]
    spr = (min(active_stacks) if active_stacks else 0) / max(pot, 1)
    f[29] = min(max(spr, 0.0), 10.0) / 10.0
    f[30] = to_call / (pot + to_call) if to_call > 0 and (pot + to_call) > 0 else 0.0
    opp_stacks = sorted((p.get("stack", 0) for p in players
                         if p.get("seat") != my_seat and not p.get("is_folded")), reverse=True)
    for i, s in enumerate(opp_stacks[:5]):
        f[31 + i] = s / STARTING_STACK

    log = state.get("action_log") or []
    n_raises, last_raiser, last_full_raise = current_street_aggression(log, players, current_bet, street_name)
    has_aggressor = last_raiser is not None or (
        current_bet > 0 and not (street_name == "preflop" and current_bet <= 100))
    f[36] = min(n_raises, 4) / 4.0
    f[37] = float(has_aggressor)
    f[38] = float(last_raiser == my_seat)
    f[39] = state.get("your_bet_this_street", 0) / STARTING_STACK
    hand_invested = _hand_invested_from_log(log, players, street_name)
    invested = hand_invested.get(my_seat, 0) if hand_invested else STARTING_STACK - my_stack
    f[40] = invested / STARTING_STACK
    f[41] = current_bet / max(pot, 1)
    f[42] = to_call / max(my_stack, 1)
    max_vill_bets = max_vill_invested = 0
    for p in players:
        if p.get("seat") != my_seat and not p.get("is_folded"):
            max_vill_bets = max(max_vill_bets, _safe_int(p.get("bet_this_street", 0)))
            seat = _safe_int(p.get("seat", -1), -1)
            vi = hand_invested.get(seat, 0) if hand_invested else STARTING_STACK - p.get("stack", STARTING_STACK)
            max_vill_invested = max(max_vill_invested, vi)
    f[43] = max_vill_bets / STARTING_STACK
    f[44] = max_vill_invested / STARTING_STACK
    f[45] = sum(1 for p in players if not p.get("is_folded")) / 6.0

    legal = compute_legal_mask(state, n_raises, last_full_raise)
    for a in range(N_ACTIONS):
        f[LEGAL_MASK_OFFSET + a] = float(legal[a])
    return f, legal
