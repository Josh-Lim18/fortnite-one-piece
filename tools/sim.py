"""Fast in-process poker simulator: paired-seed comparisons of bots.

    python3 tools/sim.py bot.py other.py --rounds 16 --hands 1000 --seed 1 [--pool a.py b.py]
    python3 tools/sim.py bot.py --vs old_bot.py --rounds 32
"""
import argparse
import glob
import hashlib
import importlib.util
import math
import multiprocessing
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kit"))
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

SEATS, BIG_BLIND = 8, 20
_JOB = {}  # per-call state handed to forked workers (factories are closures, not picklable)


def load(path):
    """Import a bot file under a unique module name and return its Agent class."""
    path = os.path.abspath(path)
    name = "simbot_" + hashlib.md5(path.encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # lets tune.py find the module's PARAMS
    sys.path.insert(0, os.path.dirname(path))
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(os.path.dirname(path))
    return mod.Agent


def _seeded(factory, seed):
    def make():
        agent = factory()
        if hasattr(agent, "rng"):
            agent.rng = random.Random(seed)
        return agent
    return make


def _play(factories, hands, seed):
    random.seed(seed)
    players = [LocalPlayer(_seeded(f, seed * 1009 + i)) for i, f in enumerate(factories)]
    chips = FixedHandsTable(players, hands=hands, seed=seed).play()["chips"]
    for i, p in enumerate(players):
        if p.stats.errors:
            print("seat %d: %d bot errors, first:\n%s" % (i, p.stats.errors, p.stats.error_samples[0]),
                  file=sys.stderr)
    return chips


def run(factories, hands, seed):
    """Play one table in-process; returns chips per seat."""
    return _play(factories, hands, seed)


def _round_setup(pool, r, seed, k):
    """Seeded fill of k seats from pool; the rng then also drives seat order and table seed."""
    rng = random.Random(seed * 1000003 + r)
    return rng, [rng.choice(pool) for _ in range(k)]


def _compare_round(r):
    j = _JOB
    rng, others = _round_setup(j["pool"], r, j["seed"], SEATS - 1)
    slot = rng.randrange(SEATS)
    table_seed = rng.randrange(1 << 30)
    out = []
    for ours in (j["candidate"], j["baseline"]):
        seats = others[:slot] + [ours] + others[slot:]
        out.append(_play(seats, j["hands"], table_seed)[slot])
    return (out[0] - out[1]) / BIG_BLIND / j["hands"] * 100


def _named_round(r):
    j = _JOB
    n = len(j["bots"])
    rng, fill = _round_setup(j["pool"], r, j["seed"], SEATS - n)
    order = list(range(n)) + [None] * len(fill)
    rng.shuffle(order)
    it = iter(fill)
    table_seed = rng.randrange(1 << 30)
    chips = _play([j["bots"][s] if s is not None else next(it) for s in order], j["hands"], table_seed)
    res = [0.0] * n
    for seat, s in enumerate(order):
        if s is not None:
            res[s] = chips[seat] / BIG_BLIND / j["hands"] * 100
    return res


def _map(fn, rounds, job):
    _JOB.clear()
    _JOB.update(job)
    with multiprocessing.get_context("fork").Pool() as pool:
        return pool.map(fn, range(rounds))


def _mean_se(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("inf")
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def compare(candidate, baseline, pool, rounds, seed, hands=1000):
    """Paired bb/100 difference (candidate - baseline) over identical deals: (mean, stderr)."""
    diffs = _map(_compare_round, rounds, dict(candidate=candidate, baseline=baseline, pool=pool,
                                              seed=seed, hands=hands))
    return _mean_se(diffs)


def default_pool():
    return sorted(glob.glob(os.path.join(ROOT, "kit/examples/*.py")) + glob.glob(os.path.join(ROOT, "opponents/*.py")))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bots", nargs="+")
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--hands", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--pool", nargs="*", default=None, help="fill-in bots (default: kit/examples + opponents)")
    ap.add_argument("--vs", help="baseline bot: print compare() for the first named bot")
    a = ap.parse_args()
    if len(a.bots) > SEATS:
        sys.exit("A table seats %d bots" % SEATS)
    pool = [load(p) for p in (a.pool if a.pool else default_pool())]
    if not pool:
        sys.exit("empty pool")
    if a.vs:
        m, se = compare(load(a.bots[0]), load(a.vs), pool, a.rounds, a.seed, a.hands)
        print("%s vs %s: %+.1f ± %.1f bb/100 (paired, %d rounds)" % (a.bots[0], a.vs, m, se, a.rounds))
        return
    bots = [load(b) for b in a.bots]
    rows = list(zip(*_map(_named_round, a.rounds, dict(bots=bots, pool=pool, seed=a.seed, hands=a.hands))))
    for name, xs in zip(a.bots, rows):
        m, se = _mean_se(xs)
        print("%-28s %+8.1f ± %.1f bb/100 (%d rounds)" % (name, m, se, a.rounds))


if __name__ == "__main__":
    main()
