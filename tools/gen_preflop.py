"""Rank the 169 starting hands by all-in equity against two random hands.

    python3 tools/gen_preflop.py > tools/preflop_order.txt

Prints the hands best to worst on one line; bot.py embeds that line as ORDER.
"""
import os
import random
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "kit"))
from engine.cards import evaluate  # noqa: E402

RANKS = "23456789TJQKA"
TRIALS = 6000
OPPONENTS = 2


def equity(name):
    hi, lo = RANKS.index(name[0]), RANKS.index(name[1])
    hero = [hi * 4, lo * 4 + (0 if name.endswith("s") else 1)]
    deck = [c for c in range(52) if c not in hero]
    rng = random.Random(name)
    score = 0.0
    for _ in range(TRIALS):
        draw = rng.sample(deck, 5 + 2 * OPPONENTS)
        board = draw[:5]
        mine = evaluate(hero + board)
        best = max(evaluate(draw[5 + 2 * k:7 + 2 * k] + board) for k in range(OPPONENTS))
        score += 1.0 if mine > best else 0.5 if mine == best else 0.0
    return score / TRIALS, name


if __name__ == "__main__":
    names = []
    for i in range(12, -1, -1):
        for j in range(i, -1, -1):
            if i == j:
                names.append(RANKS[i] * 2)
            else:
                names += [RANKS[i] + RANKS[j] + "s", RANKS[i] + RANKS[j] + "o"]
    assert len(names) == 169
    with Pool() as pool:
        ranked = sorted(pool.map(equity, names), reverse=True)
    print(" ".join(name for _, name in ranked))
