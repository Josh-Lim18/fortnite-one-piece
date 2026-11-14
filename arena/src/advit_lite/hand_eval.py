"""eval7-compatible 5-7 card hand evaluator, standard library only.

Cards are ints 0-51: suit * 13 + rank, rank 0-12 for 2..A, suits in "cdhs" order
(the layout advitrocks9's features use). evaluate() returns exactly what
eval7.evaluate() returns: hand type << 24, then up to five 4-bit rank slots
at shifts 16, 12, 8, 4, 0.
"""

_SHIFTS = (16, 12, 8, 4, 0)


def _pack(hand_type, ranks):
    value = hand_type << 24
    for rank, shift in zip(ranks, _SHIFTS):
        value |= rank << shift
    return value


def _straight_top(rank_set):
    """Highest rank topping a 5-card straight in rank_set, or -1. A plays low in the wheel."""
    for top in range(12, 3, -1):
        if all((top - i) in rank_set for i in range(5)):
            return top
    if {12, 0, 1, 2, 3} <= rank_set:
        return 3
    return -1


def evaluate(cards):
    counts = [0] * 13
    by_suit = ([], [], [], [])
    for card in cards:
        rank = card % 13
        counts[rank] += 1
        by_suit[card // 13].append(rank)

    for suited in by_suit:
        if len(suited) >= 5:
            top = _straight_top(set(suited))
            if top >= 0:
                return _pack(8, (top,))
            flush = sorted(suited, reverse=True)[:5]
            break
    else:
        flush = None

    quads = [r for r in range(12, -1, -1) if counts[r] == 4]
    trips = [r for r in range(12, -1, -1) if counts[r] == 3]
    pairs = [r for r in range(12, -1, -1) if counts[r] == 2]
    present = [r for r in range(12, -1, -1) if counts[r]]

    if quads:
        kicker = max(r for r in present if r != quads[0])
        return _pack(7, (quads[0], kicker))
    if trips and (len(trips) > 1 or pairs):
        pair = max(trips[1:] + pairs)
        return _pack(6, (trips[0], pair))
    if flush:
        return _pack(5, flush)
    top = _straight_top(set(present))
    if top >= 0:
        return _pack(4, (top,))
    if trips:
        kickers = [r for r in present if r != trips[0]][:2]
        return _pack(3, [trips[0]] + kickers)
    if len(pairs) >= 2:
        kicker = max(r for r in present if r not in pairs[:2])
        return _pack(2, (pairs[0], pairs[1], kicker))
    if pairs:
        kickers = [r for r in present if r != pairs[0]][:3]
        return _pack(1, [pairs[0]] + kickers)
    return _pack(0, present[:5])
