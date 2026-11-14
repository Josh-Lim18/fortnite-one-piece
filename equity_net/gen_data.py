"""Label random positions with Monte Carlo win/tie/lose against opponents holding hands from their range widths.

    python3 equity_net/gen_data.py --positions 200000 --samples 1000 --seed 1 --out equity_net/data

Each opponent holds a hand from the top `width` share by bot.hand_pct (0.95+ is any hand), as bot.Agent._equity
models it, but sampled exactly from the range. One JSON line per position: [hero, board, widths, [win, tie, lose]].
Standard library only; one shard file per task, so runs with different seeds can share a folder.
"""
import argparse
import json
import multiprocessing
import os
import random
import sys
import time
from bisect import bisect_right

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bot  # noqa: E402

COMBOS = sorted(((a, b) for a in range(52) for b in range(a + 1, 52)), key=lambda h: bot.hand_pct(*h))
PCTS = [bot.hand_pct(*h) for h in COMBOS]
CHUNK = 500  # positions per task and shard


def in_range(width, dead):
    k = len(COMBOS) if width >= 0.95 else bisect_right(PCTS, width)
    return [h for h in COMBOS[:k] if h[0] not in dead and h[1] not in dead]


def label(hero, board, widths, samples, rng):
    """(win, tie, lose) shares over `samples` deals: win beats every opponent, tie equals the best of them."""
    dead = set(hero) | set(board)
    ranges = [in_range(w, dead) for w in widths]
    deck = [c for c in range(52) if c not in dead]
    missing = 5 - len(board)
    score, choice, sample = bot.score, rng.choice, rng.sample
    fixed = score(hero + board) if not missing else 0
    win = tie = 0
    for _ in range(samples):
        while True:  # redraw the whole set on a clash, so hands are uniform over legal combinations
            opps = [choice(r) for r in ranges]
            taken = {c for h in opps for c in h}
            if len(taken) == 2 * len(opps):
                break
        if missing:
            full = board + [c for c in sample(deck, missing + len(taken)) if c not in taken][:missing]
            mine = score(hero + full)
        else:
            full, mine = board, fixed
        best = max(score([a, b] + full) for a, b in opps)
        if mine > best:
            win += 1
        elif mine == best:
            tie += 1
    return [win / samples, tie / samples, (samples - win - tie) / samples]


def position(rng):
    """A random spot: street 1:3:3:3 preflop to river, hands in the top 40% twice as likely, 1-3 opponents."""
    n_board = rng.choices((0, 3, 4, 5), (1, 3, 3, 3))[0]
    while True:
        cards = rng.sample(range(52), 2 + n_board)
        if bot.hand_pct(cards[0], cards[1]) <= 0.4 or rng.random() < 0.5:
            break
    n = rng.choices((1, 2, 3), (5, 3, 2))[0]
    widths = sorted((round(rng.uniform(0.05, 1.0), 3) for _ in range(n)), reverse=True)
    return cards[:2], cards[2:], widths


def _task(args):
    seed, task, positions, samples, out = args
    rng = random.Random(seed * 1000003 + task)
    path = os.path.join(out, "s%d-%05d.jsonl" % (seed, task))
    with open(path + ".tmp", "w") as f:
        for _ in range(positions):
            hero, board, widths = position(rng)
            f.write(json.dumps([hero, board, widths, label(hero, board, widths, samples, rng)]) + "\n")
    os.replace(path + ".tmp", path)  # a killed run leaves no half-written shard
    return positions


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--positions", type=int, required=True)
    ap.add_argument("--samples", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    tasks = [(a.seed, t, min(CHUNK, a.positions - t * CHUNK), a.samples, a.out)
             for t in range(-(-a.positions // CHUNK))]
    t0, done = time.time(), 0
    with multiprocessing.Pool(a.workers) as pool:
        for n in pool.imap_unordered(_task, tasks):
            done += n
            print("\r%d/%d positions, %.0f s" % (done, a.positions, time.time() - t0), end="", file=sys.stderr)
    print(file=sys.stderr)


if __name__ == "__main__":
    main()
