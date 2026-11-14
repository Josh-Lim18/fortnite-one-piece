"""Score the opponent model on held-out rounds: each round replays through a fresh profiler and every opponent
action is scored by the log-loss of the probability predicted just before it.

    python3 model/evaluate.py model/sim     # held-out rounds of the folder, constants from model/fitted.py
    python3 model/evaluate.py model/sim --fitted other_fitted.py
"""
import argparse
import math
import random
import multiprocessing
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dataset import load, split, summaries  # noqa: E402
from profiler import SAMPLES, TEMPER, Profiler, cell, decisions, showdown_buckets  # noqa: E402

SEEN = (0, 25, 100, 300)          # hands-seen bucket starts
CHECKPOINTS = (25, 100, 300, 1000)  # hands after which a seat's top type is checked
CONF = (0.4, 0.6, 0.8, 0.95, 1.01)  # top type posterior bucket ends, for the calibration table
TEMPERS = (0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.1)
VERSIONS = (("prior", dict(counts=False, types=False)), ("counts", dict(types=False)), ("full", {}))


def _bucket(hand):
    return sum(hand - 1 >= s for s in SEEN) - 1


def replay(job):
    """Sums for one round: log-loss and count per version and hands-seen bucket, type matches per checkpoint
    and bot, calibration of the top type posterior after every hand, log-loss of the fitted type ranges against
    every dealt hand (simulated files only), and time spent in observe and predict."""
    path, fitted, temper = job
    rnd, bots = load(path)
    hands = list(summaries(rnd))
    n = hands[0]["seats"]
    models = {name: Profiler(n, fitted, temper=temper, **kw) for name, kw in VERSIONS}
    loss = {name: [[0.0, 0] for _ in SEEN] for name in models}
    match = {}
    calib = [[0.0, 0, 0] for _ in CONF]  # per bucket: sum of top posterior, hits, (seat, hand)s
    nll = [0.0, 0]                       # -log posterior of the seat's usual type, after every hand
    rng_loss = [0.0, 0]                  # -log range probability of the hand's true strength bucket
    t_obs = t_pred = 0.0
    calls = 0
    for s in hands:
        b = _bucket(s["hand_number"])
        acts = list(decisions(s["history"], n))
        last = {(d[0], d[1]): d[5] for d in acts}
        dealt = {seat: c for seat, c in s["dealt"].items() if any(a for (st, _), a in last.items() if st == seat)}
        strength = showdown_buckets(dealt, s["board"], random.Random(s["hand_number"]), SAMPLES) if dealt else {}
        for (seat, street), action in last.items():
            if action and seat in strength and street < len(strength[seat]):
                rng_loss[0] -= math.log(max(models["full"].range(seat, street, action)[strength[seat][street]], 1e-9))
                rng_loss[1] += 1
        for seat, street, size, raises, _, action in acts:
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
        if bots:
            full = models["full"]
            for seat, bot in enumerate(bots):
                w = full.type_posterior(seat)
                top, truth = max(w), fitted["bot_type"].get(bot)
                hit = w.index(top) == truth
                c = calib[sum(top >= e for e in CONF[:-1])]
                c[0] += top
                c[1] += hit
                c[2] += 1
                if truth is not None:
                    nll[0] -= math.log(max(w[truth], 1e-12))
                    nll[1] += 1
                if s["hand_number"] in CHECKPOINTS:
                    m = match.setdefault((bot, s["hand_number"]), [0, 0, 0])
                    m[0] += hit
                    m[1] += 1
                    m[2] += top > 0.95
    return loss, match, calib, nll + rng_loss, t_obs, t_pred, calls


def score(fitted, files, temper=TEMPER):
    """Pooled results over round files; "full", "counts", "prior" are overall log-loss per decision."""
    with multiprocessing.Pool() as p:
        parts = p.map(replay, [(f, fitted, temper) for f in files])
    loss = {name: [[0.0, 0] for _ in SEEN] for name, _ in VERSIONS}
    match = {}
    calib = [[0.0, 0, 0] for _ in CONF]
    nll = [0.0, 0, 0.0, 0]
    t_obs = t_pred = 0.0
    calls = 0
    for l, m, cb, nl, to, tp, c in parts:
        for acc, x in zip(calib + [nll], cb + [nl]):
            for i, v in enumerate(x):
                acc[i] += v
        for name in loss:
            for b in range(len(SEEN)):
                loss[name][b][0] += l[name][b][0]
                loss[name][b][1] += l[name][b][1]
        for key, (hit, n, top) in m.items():
            acc = match.setdefault(key, [0, 0, 0.0])
            acc[0] += hit
            acc[1] += n
            acc[2] += top
        t_obs, t_pred, calls = t_obs + to, t_pred + tp, calls + c
    out = {name: sum(x for x, _ in v) / sum(n for _, n in v) for name, v in loss.items()}
    for other in ("prior", "counts"):  # paired by round: full minus the weaker version, mean and standard error
        d = [(sum(x for x, _ in l["full"]) - sum(x for x, _ in l[other])) / sum(n for _, n in l["full"]) for l, *_ in parts]
        mean = sum(d) / len(d)
        se = (sum((x - mean) ** 2 for x in d) / (len(d) - 1) / len(d)) ** 0.5 if len(d) > 1 else float("inf")
        out["full_vs_" + other] = (mean, se)
    out.update(loss=loss, match=match, calib=calib, type_nll=nll[0] / max(nll[1], 1),
               range_nll=nll[2] / nll[3] if nll[3] else None,
               calib_gap=max(abs(c - h) / n for c, h, n in calib if n), us_observe=1e6 * t_obs / calls, us_predict=1e6 * t_pred / calls, rounds=len(files))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder")
    ap.add_argument("--temper", type=float, default=TEMPER)
    ap.add_argument("--fitted", help="constants file to score instead of model/fitted.py")
    ap.add_argument("--fit-temper", action="store_true",
                    help="print the type log-loss of each candidate temper on the fitting rounds, then use the best")
    a = ap.parse_args()
    if a.fitted:
        scope = {}
        with open(a.fitted) as f:
            exec(f.read(), scope)  # a constants file written by fit.py
        FITTED = scope["FITTED"]
    else:
        from fitted import FITTED
    train, test = split(a.folder)
    if a.fit_temper:
        fits = []
        for t in TEMPERS:
            r = score(FITTED, train, t)
            fits.append((r["type_nll"], t))
            print("temper %.3f: -log posterior of the usual type %.4f, worst calibration gap %.3f on %d fitting rounds"
                  % (t, r["type_nll"], r["calib_gap"], len(train)))
        a.temper = min(fits)[1]
        print("best temper %.3f\n" % a.temper)
    r = score(FITTED, test, a.temper)
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
            print("  %-44s" % (bot or "all seats") + "".join("%7.0f%%" % (100.0 * sum(h for h, _, _ in x) / sum(n for _, n, _ in x))
                                                             for x in cells) + "   (%d seats)" % sum(n for _, n, _ in cells[0]))
        cells = [[v for key, v in r["match"].items() if key[1] == c] for c in CHECKPOINTS]
        print("  %-44s" % "seats with top posterior over 0.95" + "".join(
            "%7.0f%%" % (100.0 * sum(t for _, _, t in x) / sum(n for _, n, _ in x)) for x in cells))
        print("\ncalibration at temper %.2f, every (seat, hand): top type posterior against how often that type is the"
              " bot's usual one" % a.temper)
        print("  posterior    mean   hit rate   (seat, hand)s")
        for lo, hi, (conf, hits, n) in zip((0.0,) + CONF, CONF, r["calib"]):
            if n:
                print("  %.2f-%.2f  %6.3f  %8.3f  %10d" % (lo, min(hi, 1.0), conf / n, hits / n, n))
        print("  -log posterior of the usual type: %.4f per (seat, hand); worst gap %.3f" % (r["type_nll"], r["calib_gap"]))
    if r["range_nll"] is not None:
        print("range tables against every dealt hand: %.4f nats per (seat, street) that called or raised" % r["range_nll"])
    print("\nprofiler time: observe %.1f us, predict %.1f us per call" % (r["us_observe"], r["us_predict"]))


if __name__ == "__main__":
    main()
