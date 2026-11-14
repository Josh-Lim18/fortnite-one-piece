"""Score the opponent model on held-out rounds: each round replays through a fresh profiler and every opponent
action is scored by the log-loss of the probability predicted just before it.

    python3 model/evaluate.py model/sim     # held-out rounds of the folder, constants from model/fitted.py
"""
import argparse
import math
import multiprocessing
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dataset import load, split, summaries  # noqa: E402
from profiler import Profiler, cell, decisions  # noqa: E402

SEEN = (0, 25, 100, 300)          # hands-seen bucket starts
CHECKPOINTS = (25, 100, 300, 1000)  # hands after which a seat's top type is checked
VERSIONS = (("prior", dict(counts=False, types=False)), ("counts", dict(types=False)), ("full", {}))


def _bucket(hand):
    return sum(hand - 1 >= s for s in SEEN) - 1


def replay(job):
    """Sums for one round: log-loss and count per version and hands-seen bucket, type matches per checkpoint
    and bot, and time spent in observe and predict."""
    path, fitted = job
    rnd, bots = load(path)
    hands = list(summaries(rnd))
    n = hands[0]["seats"]
    models = {name: Profiler(n, fitted, **kw) for name, kw in VERSIONS}
    loss = {name: [[0.0, 0] for _ in SEEN] for name in models}
    match = {}
    t_obs = t_pred = 0.0
    calls = 0
    for s in hands:
        b = _bucket(s["hand_number"])
        for seat, street, size, raises, _, action in decisions(s["history"], n):
            if seat == rnd["seat"]:
                continue
            c = cell(street, size, raises)
            for name, m in models.items():
                t0 = time.perf_counter()
                p = m.predict(seat, c)
                t1 = time.perf_counter()
                m.observe(seat, c, action, s["hand_number"])
                t2 = time.perf_counter()
                if name == "full":
                    t_pred += t1 - t0
                    t_obs += t2 - t1
                    calls += 1
                loss[name][b][0] -= math.log(max(p[action], 1e-9))
                loss[name][b][1] += 1
        if bots and s["hand_number"] in CHECKPOINTS:
            full = models["full"]
            for seat, bot in enumerate(bots):
                w = full.type_posterior(seat)
                hit = w.index(max(w)) == fitted["bot_type"].get(bot)
                m = match.setdefault((bot, s["hand_number"]), [0, 0])
                m[0] += hit
                m[1] += 1
    return loss, match, t_obs, t_pred, calls


def score(fitted, files):
    """Pooled results over round files; "full", "counts", "prior" are overall log-loss per decision."""
    with multiprocessing.Pool() as p:
        parts = p.map(replay, [(f, fitted) for f in files])
    loss = {name: [[0.0, 0] for _ in SEEN] for name, _ in VERSIONS}
    match = {}
    t_obs = t_pred = 0.0
    calls = 0
    for l, m, to, tp, c in parts:
        for name in loss:
            for b in range(len(SEEN)):
                loss[name][b][0] += l[name][b][0]
                loss[name][b][1] += l[name][b][1]
        for key, (hit, n) in m.items():
            acc = match.setdefault(key, [0, 0])
            acc[0] += hit
            acc[1] += n
        t_obs, t_pred, calls = t_obs + to, t_pred + tp, calls + c
    out = {name: sum(x for x, _ in v) / sum(n for _, n in v) for name, v in loss.items()}
    for other in ("prior", "counts"):  # paired by round: full minus the weaker version, mean and standard error
        d = [(sum(x for x, _ in l["full"]) - sum(x for x, _ in l[other])) / sum(n for _, n in l["full"]) for l, *_ in parts]
        mean = sum(d) / len(d)
        se = (sum((x - mean) ** 2 for x in d) / (len(d) - 1) / len(d)) ** 0.5 if len(d) > 1 else float("inf")
        out["full_vs_" + other] = (mean, se)
    out.update(loss=loss, match=match, us_observe=1e6 * t_obs / calls, us_predict=1e6 * t_pred / calls, rounds=len(files))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    a = ap.parse_args()
    from fitted import FITTED
    _, test = split(a.folder)
    r = score(FITTED, test)
    print("held-out: %d rounds of %s. Log-loss in nats per opponent decision (lower is better)." % (r["rounds"], a.folder))
    print("hands seen        " + "".join("%12s" % ("%d-%s" % (s, e)) for s, e in zip(SEEN, SEEN[1:] + ("",)))
          + "         all")
    for name, label in (("prior", "prior only"), ("counts", "seat counts+prior"), ("full", "full with types")):
        print("%-18s" % label + "".join("%12.4f" % (x / n) for x, n in r["loss"][name]) + "%12.4f" % r[name])
    print("decisions         " + "".join("%12d" % n for _, n in r["loss"]["full"]))
    for other in ("prior", "counts"):
        print("full minus %-6s %+.4f +- %.4f (one standard error, paired by round)" % ((other,) + r["full_vs_" + other]))
    bots = sorted({b for b, _ in r["match"]})
    if bots:
        print("\ntop type is the bot's usual type, after hands: " + "".join("%8d" % c for c in CHECKPOINTS))
        for bot in bots + [None]:
            cells = [[r["match"][key] for key in r["match"] if key[1] == c and bot in (None, key[0])] for c in CHECKPOINTS]
            print("  %-44s" % (bot or "all seats") + "".join("%7.0f%%" % (100.0 * sum(h for h, _ in x) / sum(n for _, n in x))
                                                             for x in cells) + "   (%d seats)" % sum(n for _, n in cells[0]))
    print("\nprofiler time: observe %.1f us, predict %.1f us per call" % (r["us_observe"], r["us_predict"]))


if __name__ == "__main__":
    main()
