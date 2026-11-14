"""The one feature encoder for the equity network, used by train.py and pasted into bot.py. Standard library only.

Cards are ints as in bot.card: rank * 4 + suit. Widths are each opponent's range as the top share of hands.
"""
N_FEATURES = 57


def net_features(hero, board, widths):
    """13 hero rank counts, 13 board rank counts, the flushiest suit (13 board ranks in it, whether each hero
    card is in it), the other three suits' (hero, board) counts, street one-hot, opponents one-hot, widths sorted.
    Suits are ordered by their whole content, so renaming suits never changes the output."""
    x = [0.0] * N_FEATURES
    for c in hero:
        x[c >> 2] += 1.0
    for c in board:
        x[13 + (c >> 2)] += 1.0
    suits = []
    for s in range(4):
        hm = bm = hn = bn = 0
        for c in hero:
            if c & 3 == s:
                hm |= 1 << (c >> 2)
                hn += 1
        for c in board:
            if c & 3 == s:
                bm |= 1 << (c >> 2)
                bn += 1
        suits.append((hn + bn, bn, hm, bm, hn))
    suits.sort(reverse=True)
    _, bn, hm, bm, hn = suits[0]
    for r in range(13):
        if bm >> r & 1:
            x[26 + r] = 1.0
    hi, lo = max(hero[0] >> 2, hero[1] >> 2), min(hero[0] >> 2, hero[1] >> 2)
    x[39] = 1.0 if hm >> hi & 1 else 0.0
    x[40] = 1.0 if hi != lo and hm >> lo & 1 else 0.0
    for k in range(3):
        x[41 + 2 * k] = float(suits[k + 1][4])
        x[42 + 2 * k] = float(suits[k + 1][1])
    x[47 + (0 if not board else len(board) - 2)] = 1.0
    ws = sorted((1.0 if w >= 0.95 else w for w in widths[:3]), reverse=True)  # bot.py treats 0.95+ as any hand
    x[51 + len(ws) - 1] = 1.0
    for k, w in enumerate(ws):
        x[54 + k] = w
    return x
