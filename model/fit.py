"""Fit the layer 2 opponent model on the training rounds of a folder and write model/fitted.py.

    python3 model/fit.py model/sim            # k chosen by held-out log-loss among --ks
    python3 model/fit.py hands/ --ks 4 5 6
"""
import argparse
import functools
import json
import multiprocessing
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dataset import rows, split  # noqa: E402
from evaluate import score  # noqa: E402
from profiler import BUCKETS, CELLS, cell  # noqa: E402

MIN_N = 5          # a seat counts toward a cell's spread once it made this many decisions there
TYPE_SHRINK = 5.0  # decisions of the population rate added to each type's pooled counts
RANGE_SHRINK = 20.0
FEATURE_SHARE = 0.002  # cells rarer than this share of decisions are left out of clustering
SHOWDOWN_NOTE = ("Ranges come from hands shown at showdown only: a biased sample (hands that fold never show, "
                 "bluffs that win uncalled never show), shrunk toward the type's whole-street range when sparse.")
DEALT_NOTE = ("Ranges come from every hand dealt (simulated rounds keep all hole cards), shrunk toward the type's "
              "whole-street range when sparse.")


def summarise(path, showdown_only=False):
    """Per opponent seat of a round: its bot (None for real data), action counts per cell, and (street, last
    action, strength bucket) for each street of each hand whose cards are known."""
    out = {}
    for r in rows(path, showdown_only=showdown_only):
        s = out.setdefault(r["seat"], {"bot": r["bot"], "counts": [0] * (CELLS * 3), "last": {}, "dealt": False})
        s["dealt"] |= r["dealt"]
        s["counts"][r["cell"] * 3 + r["action"]] += 1
        if r["strength"] is not None:
            s["last"][r["hand"], r["street"]] = (("preflop", "flop", "turn", "river").index(r["street"]),
                                                 r["action"], r["strength"])
    return [{"bot": s["bot"], "counts": s["counts"], "shows": list(s["last"].values()), "dealt": s["dealt"]}
            for s in out.values()]


def norm(xs):
    z = sum(xs)
    return [x / z for x in xs]


def eb_weight(groups):
    """Prior weight, in decisions, from how much seats really differ from their mean: the spread of their
    observed rates minus the spread sampling noise alone gives. groups: (counts[3], mean[3]) per seat."""
    var = spread = noise = 0.0
    used = 0
    for c, mean in groups:
        n = sum(c)
        if n < MIN_N:
            continue
        used += 1
        for a in (0, 1, 2):
            v = mean[a] * (1 - mean[a])
            var += v
            spread += (c[a] / n - mean[a]) ** 2
            noise += v / n
    if used < 10 or var == 0:
        return None
    return min(1000.0, max(1.0, var / max(spread - noise, 1e-9) - 1))


def weights(groups_per_cell):
    w = [eb_weight(g) for g in groups_per_cell]
    known = sorted(x for x in w if x is not None)
    fill = known[len(known) // 2] if known else 20.0
    return [round(fill if x is None else x, 1) for x in w]


def kmeans(points, k, rng, iters=60, restarts=6):
    best = None
    for _ in range(restarts):
        centres = [rng.choice(points)]
        while len(centres) < k:  # k-means++ seeding
            d = [min(sum((a - b) ** 2 for a, b in zip(p, c)) for c in centres) for p in points]
            x, acc = rng.random() * sum(d), 0.0
            for p, dp in zip(points, d):
                acc += dp
                if acc >= x:
                    centres.append(p)
                    break
        for _ in range(iters):
            assign = [min(range(k), key=lambda j: sum((a - b) ** 2 for a, b in zip(p, centres[j]))) for p in points]
            new = []
            for j in range(k):
                members = [p for p, a in zip(points, assign) if a == j] or [rng.choice(points)]
                new.append([sum(col) / len(members) for col in zip(*members)])
            if new == centres:
                break
            centres = new
        inertia = sum(sum((a - b) ** 2 for a, b in zip(p, centres[j])) for p, j in zip(points, assign))
        if best is None or inertia < best[0]:
            best = (inertia, assign)
    return best[1]


def fit(seats, k, seed=1):
    """The FITTED dict the profiler reads, from seat summaries."""
    total = [sum(s["counts"][i] for s in seats) for i in range(CELLS * 3)]
    pop = [norm([total[c * 3 + a] + 0.5 for a in (0, 1, 2)]) for c in range(CELLS)]
    seen = [sum(total[c * 3:c * 3 + 3]) for c in range(CELLS)]
    share = [x / sum(seen) for x in seen]
    pop_m = weights([[(s["counts"][c * 3:c * 3 + 3], pop[c]) for s in seats] for c in range(CELLS)])

    def shrunk(counts, c, mean, m):
        return [(counts[c * 3 + a] + m * mean[a]) / (sum(counts[c * 3:c * 3 + 3]) + m) for a in (0, 1, 2)]

    feats = [c for c in range(CELLS) if share[c] >= FEATURE_SHARE]
    points = [[share[c] ** 0.5 * x for c in feats for x in shrunk(s["counts"], c, pop[c], pop_m[c])] for s in seats]
    assign = kmeans(points, k, random.Random(seed))
    types = []
    for t in range(k):
        pooled = [sum(s["counts"][i] for s, a in zip(seats, assign) if a == t) for i in range(CELLS * 3)]
        types.append([[round(x, 3) for x in norm([max(p, 1e-3) for p in shrunk(pooled, c, pop[c], TYPE_SHRINK)])]
                      for c in range(CELLS)])
    type_m = weights([[(s["counts"][c * 3:c * 3 + 3], types[a][c]) for s, a in zip(seats, assign)]
                      for c in range(CELLS)])

    pop_street = [[RANGE_SHRINK / BUCKETS] * BUCKETS for _ in range(4)]
    counts = [[[[0.0] * BUCKETS for _ in range(2)] for _ in range(4)] for _ in range(k)]
    for s, t in zip(seats, assign):
        for street, action, b in s["shows"]:
            if action:
                counts[t][street][action - 1][b] += 1
                pop_street[street][b] += 1
    ranges = []
    for t in range(k):
        rt = []
        for street in range(4):
            pooled = [x + y for x, y in zip(*counts[t][street])]
            base = norm([x + RANGE_SHRINK * p for x, p in zip(pooled, norm(pop_street[street]))])
            rt.append([[round(p, 3) for p in norm([x + RANGE_SHRINK * q for x, q in zip(cs, base)])]
                       for cs in counts[t][street]])
        ranges.append(rt)

    members = {}
    for s, t in zip(seats, assign):
        if s["bot"]:
            members.setdefault(s["bot"], [0] * k)[t] += 1
    return {"pop": [[round(x, 3) for x in p] for p in pop], "pop_m": pop_m,
            "type_prior": [round(assign.count(t) / len(seats), 3) for t in range(k)], "types": types,
            "type_m": type_m, "ranges": ranges, "share": [round(x, 5) for x in share],
            "bot_type": {b: m.index(max(m)) for b, m in members.items()}, "members": members}


def describe(f):
    """One line per type: its share, the bots it holds and its headline rates."""
    groups = {"open": [cell(0, s, 0) for s in (1, 2, 3, 4)], "vs raise": [cell(0, s, r) for s in range(1, 5) for r in (1, 2)],
              "checked to": [cell(st, 0, 0) for st in (1, 2, 3)], "vs bet": [cell(st, s, r) for st in (1, 2, 3)
                                                                             for s in range(1, 5) for r in (1, 2)]}

    def rate(table, cells, a):
        w = sum(f["share"][c] for c in cells)
        return 100 * sum(f["share"][c] * table[c][a] for c in cells) / w

    print("type share  open f/c/r   vs raise f/c/r  checked-to bet  vs bet f/c/r   bots (seat-rounds)")
    for t, table in enumerate(f["types"]):
        bots = ", ".join("%s %d" % (os.path.basename(b)[:-3], m[t]) for b, m in sorted(f["members"].items()) if m[t])
        print("%4d %5.2f  %3.0f/%3.0f/%3.0f  %4.0f/%3.0f/%3.0f  %8.0f%%      %3.0f/%3.0f/%3.0f   %s" % (
            t, f["type_prior"][t], *[rate(table, groups["open"], a) for a in (0, 1, 2)],
            *[rate(table, groups["vs raise"], a) for a in (0, 1, 2)], rate(table, groups["checked to"], 2),
            *[rate(table, groups["vs bet"], a) for a in (0, 1, 2)], bots))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--ks", type=int, nargs="+", default=[4, 5, 6])
    ap.add_argument("--out", default=os.path.join(HERE, "fitted.py"))
    ap.add_argument("--showdown-ranges", action="store_true",
                    help="fit ranges from showdown hands only even when the files keep every dealt hand")
    a = ap.parse_args()
    train, _ = split(a.folder)
    val = train[3::4]
    with multiprocessing.Pool() as p:
        per_round = p.map(functools.partial(summarise, showdown_only=a.showdown_ranges), train)
        sub = [s for path, r in zip(train, per_round) if path not in val for s in r]
        fits = p.starmap(fit, [(sub, k) for k in a.ks])
    seats = [s for r in per_round for s in r]
    print("%d training rounds, %d opponent seat-rounds; k chosen on %d of those rounds held back" % (
        len(train), len(seats), len(val)))
    best = None
    for k, f in zip(a.ks, fits):
        ll = score(f, val)["full"]
        print("k=%d  held-out log-loss %.4f nats per decision" % (k, ll))
        if best is None or ll < best[1]:
            best = (k, ll)
    f = fit(seats, best[0])
    dealt = not a.showdown_ranges and any(s["dealt"] for s in seats)
    note = DEALT_NOTE if dealt else SHOWDOWN_NOTE
    print("chose k=%d; %s" % (best[0], note))
    describe(f)
    print("prior weight in decisions (median over cells): population %.0f, within type %.0f" % (
        sorted(f["pop_m"])[CELLS // 2], sorted(f["type_m"])[CELLS // 2]))
    del f["members"]
    with open(a.out, "w") as out:
        out.write('"""Layer 2 opponent model constants, written by model/fit.py from %d seat-rounds of %s; k=%d.\n'
                  '%s\nKeys: pop/types [cell][fold, call, raise]; pop_m/type_m prior weight in decisions per cell;\n'
                  'ranges [type][street][call, raise][strength bucket]; share of decisions per cell; bot_type maps\n'
                  'each training bot to its usual type (for evaluate.py; the profiler ignores it)."""\n'
                  % (len(seats), os.path.basename(os.path.normpath(a.folder)), best[0], note))
        out.write("FITTED = " + json.dumps(f, separators=(",", ":")) + "\n")
    print("wrote %s, %d bytes" % (a.out, os.path.getsize(a.out)))


if __name__ == "__main__":
    main()
