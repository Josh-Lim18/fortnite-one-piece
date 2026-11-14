"""Hill-climb bot.PARAMS against an incumbent with paired-seed comparisons.

    python3 tools/tune.py --iters 30 --rounds 16 [--keys value bet_frac] [--pool a.py b.py] [--bot bot.py]
"""
import argparse
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

SKIP = {"trials", "decision_ms", "round_budget_s"}


def search_keys(params, named):
    if named:
        return named
    # shortcut: zero-valued params (e.g. risk) can't move under a multiplicative step, so they need --keys and a nonzero start.
    return [k for k, v in params.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
            and k not in SKIP and not k.startswith("prior_") and v != 0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot", default=os.path.join(sim.ROOT, "bot.py"))
    ap.add_argument("--pool", nargs="*", default=None)
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--hands", type=int, default=1000)
    ap.add_argument("--iters", type=int, default=20)
    ap.add_argument("--keys", nargs="*", default=None)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(sim.ROOT, "notes", "tuned.json"))
    a = ap.parse_args()

    agent = sim.load(a.bot)
    base = sys.modules[agent.__module__].PARAMS
    keys = search_keys(base, a.keys)
    missing = [k for k in keys if k not in base]
    if missing:
        sys.exit("unknown keys: %s" % missing)
    pool = [sim.load(p) for p in (a.pool if a.pool else sim.default_pool())]
    rng = random.Random(a.seed)
    incumbent = {}
    for it in range(1, a.iters + 1):
        cand = dict(incumbent)
        for k in rng.sample(keys, min(len(keys), rng.randint(1, 3))):
            v = cand.get(k, base[k]) * math.exp(rng.gauss(0, 0.3))
            if isinstance(base[k], float) and 0 <= base[k] <= 1:
                v = min(v, 1.0)
            cand[k] = round(v) if isinstance(base[k], int) else v
        changed = {k: round(v, 4) for k, v in cand.items() if incumbent.get(k) != v}
        m, se = sim.compare(lambda c=cand: agent(params=c), lambda i=dict(incumbent): agent(params=i),
                            pool, a.rounds, a.seed + it, a.hands)
        ok = m > 2 * se
        print("%3d %-8s %+7.1f ± %.1f  %s" % (it, "ACCEPT" if ok else "reject", m, se, changed), flush=True)
        if ok:
            incumbent = cand
            with open(a.out, "w") as f:
                json.dump(incumbent, f, indent=2, sort_keys=True)
    print("incumbent overrides:", incumbent)


if __name__ == "__main__":
    main()
