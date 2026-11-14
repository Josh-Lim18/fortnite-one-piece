"""Paired comparisons: candidates and an incumbent play the same deals against an opponent pool.

    python3 evaluation/run.py --incumbent kit/bot.py bot.py [more.py ...] [--rounds 32] [--hands 1000] [--seed 1]
    python3 evaluation/run.py --incumbent kit/bot.py bot.py --final     # the held-out seeds

Each round seeds the deck, the opponents chosen from the pool and their randomness; the incumbent and every
candidate take the same seat (rotating with the round) at that same table. Runs in-process for speed, with no
time limits enforced (tests/check_submission.py plays under the real ones). Writes one JSON record to
evaluation/results/<UTC time>-<short id>.json.
"""
import argparse
import datetime
import glob
import hashlib
import importlib.util
import json
import math
import multiprocessing
import os
import random
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HOLDOUT = os.path.join(HERE, "holdout_seeds.txt")
SEATS, BIG_BLIND = 8, 20
TIMEOUT_MS, BANK_MS = 10.0, 10_000.0  # the tournament's limits, measured here but not enforced
_JOB = {}  # per-call state handed to forked workers (factories are closures, not picklable)
FixedHandsTable = LocalPlayer = DEFAULT_CONFIG = None


def use_kit(kit):
    """Put the starter kit's engine on the path; stop with one sentence when it isn't there."""
    global FixedHandsTable, LocalPlayer, DEFAULT_CONFIG
    kit = os.path.abspath(kit)
    if not os.path.isfile(os.path.join(kit, "engine", "game.py")):
        sys.exit("No starter kit at %s: pass --kit PATH to the organisers' kit folder (the one holding engine/)."
                 % kit)
    sys.path.insert(0, kit)
    from engine import FixedHandsTable, DEFAULT_CONFIG
    from engine.players import LocalPlayer
    return kit


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def engine_revision(kit):
    """One hash over the kit's engine files, so records from different engines are never mixed."""
    h = hashlib.sha256()
    for path in sorted(glob.glob(os.path.join(kit, "engine", "*.py"))):
        h.update(os.path.basename(path).encode() + b"\0" + open(path, "rb").read())
    return h.hexdigest()


def holdout_seeds():
    with open(HOLDOUT) as f:
        return [int(line) for line in f if line.strip() and not line.startswith("#")]


def load(path):
    """Import a bot file under a unique module name and return its Agent class."""
    path = os.path.abspath(path)
    name = "evalbot_" + hashlib.md5(path.encode()).hexdigest()[:10]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
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


def _count_timeouts(player):
    """Count decisions slower than the tournament limit; in-process nothing is cut off."""
    act = player.act

    def timed(state):
        before = player.stats.total_ms
        out = act(state)
        player.stats.timeouts += player.stats.total_ms - before > TIMEOUT_MS
        return out
    player.act = timed


def play(factories, hands, seed, watch=None):
    """Play one table in-process; returns (chips per seat, players)."""
    random.seed(seed)
    players = [LocalPlayer(_seeded(f, seed * 1009 + i)) for i, f in enumerate(factories)]
    if watch is not None:
        _count_timeouts(players[watch])
    chips = FixedHandsTable(players, hands=hands, seed=seed).play()["chips"]
    for i, p in enumerate(players):
        if p.stats.errors:
            print("seat %d: %d bot errors, first:\n%s" % (i, p.stats.errors, p.stats.error_samples[0]),
                  file=sys.stderr)
    return chips, players


def _round(r):
    """One deal set: the opponents and seat are fixed by the round, then each of our bots plays it."""
    j = _JOB
    seed = j["seeds"][r]
    rng = random.Random(seed)
    others = [rng.randrange(len(j["pool"])) for _ in range(SEATS - 1)]
    seat = r % SEATS
    bots = []
    for bot in j["bots"]:
        seats = [j["pool"][k] for k in others]
        seats.insert(seat, bot)
        chips, players = play(seats, j["hands"], seed, watch=seat)
        st = players[seat].stats
        bots.append({"chips": chips[seat], "errors": st.errors, "timeouts": st.timeouts,
                     "decisions": st.decisions, "think_ms": round(st.total_ms, 1), "max_ms": round(st.max_ms, 2)})
    return {"seed": seed, "seat": seat, "opponents": others, "bots": bots}


def mean_se(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, None
    return m, math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n)


def compare(bots, pool, seeds, hands):
    """Play every round for bots[0] (the incumbent) and the rest; returns the per-round results."""
    _JOB.clear()
    _JOB.update(bots=bots, pool=pool, seeds=seeds, hands=hands)
    with multiprocessing.get_context("fork").Pool() as workers:
        return workers.map(_round, range(len(seeds)))


def summary(rounds, k, hands):
    """Bot k's totals, and its paired difference from the incumbent (bot 0) in bb/100."""
    rows = [rd["bots"][k] for rd in rounds]
    diffs = [(rd["bots"][k]["chips"] - rd["bots"][0]["chips"]) / BIG_BLIND / hands * 100 for rd in rounds]
    m, se = mean_se(diffs)
    chips = sum(r["chips"] for r in rows)
    return {"chips": chips, "bb100": round(chips / BIG_BLIND / (hands * len(rounds)) * 100, 2),
            "diff_bb100": round(m, 2), "se_bb100": None if se is None else round(se, 2),
            "round_diffs": [round(d, 3) for d in diffs],
            "errors": sum(r["errors"] for r in rows), "timeouts": sum(r["timeouts"] for r in rows),
            "decisions": sum(r["decisions"] for r in rows),
            "bank_outs": sum(r["think_ms"] > BANK_MS for r in rows),
            "worst_round_think_s": round(max(r["think_ms"] for r in rows) / 1000, 3),
            "worst_decision_ms": max(r["max_ms"] for r in rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("candidates", nargs="+")
    ap.add_argument("--incumbent", required=True, help="the bot to beat")
    ap.add_argument("--pool", nargs="*", help="opponent bots (default: evaluation/opponents/*.py)")
    ap.add_argument("--rounds", type=int, default=32)
    ap.add_argument("--hands", type=int, default=1000, help="hands per round (tournament: 1000)")
    ap.add_argument("--seed", type=int, default=1, help="development seeds start here")
    ap.add_argument("--final", action="store_true", help="play the held-out seeds (rounds = their count)")
    ap.add_argument("--kit", default=os.path.join(REPO, "kit"), help="the organisers' starter kit (default: kit/)")
    ap.add_argument("--out", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    kit = use_kit(a.kit)

    held = holdout_seeds()
    if a.final:
        seeds = held
    else:
        seeds = [a.seed * 1000003 + r for r in range(a.rounds)]
        if set(seeds) & set(held):
            sys.exit("Those seeds include held-out seeds from %s; pick another --seed, or pass --final."
                     % os.path.relpath(HOLDOUT))
    if len(seeds) < 2:
        sys.exit("Need at least 2 rounds for a standard error.")
    pool_paths = sorted(os.path.abspath(p) for p in (a.pool or glob.glob(os.path.join(HERE, "opponents", "*.py"))))
    if not pool_paths:
        sys.exit("Empty opponent pool.")
    paths = [os.path.abspath(p) for p in [a.incumbent] + a.candidates]
    for p in paths + pool_paths:
        if not os.path.isfile(p):
            sys.exit("Can't find bot file: %s" % p)
    if len(set(paths)) != len(paths):
        sys.exit("Each bot file can only be named once.")

    rounds = compare([load(p) for p in paths], [load(p) for p in pool_paths], seeds, a.hands)

    def rel(p):
        return os.path.relpath(p, REPO)
    bots = [dict(path=rel(p), sha256=sha256(p), **summary(rounds, k, a.hands)) for k, p in enumerate(paths)]
    now = datetime.datetime.now(datetime.timezone.utc)
    rid = uuid.uuid4().hex[:8]
    record = {
        "id": rid, "time": now.isoformat(timespec="seconds"), "final": a.final,
        "engine_revision": engine_revision(kit), "kit": rel(kit),
        "incumbent": bots[0], "candidates": bots[1:],
        "opponents": [{"path": rel(p), "sha256": sha256(p)} for p in pool_paths],
        "settings": {"rounds": len(seeds), "hands": a.hands, "seats": SEATS, "big_blind": BIG_BLIND,
                     "betting": DEFAULT_CONFIG["betting"], "raise_cap": DEFAULT_CONFIG["raise_cap"],
                     "base_seed": None if a.final else a.seed, "in_process": True,
                     "timeout_ms": TIMEOUT_MS, "bank_ms": BANK_MS, "python": sys.version.split()[0],
                     "note": "in-process: timeouts count decisions over timeout_ms and bank_outs count rounds over "
                             "bank_ms, but nothing is cut off"},
        "rounds": rounds,
    }
    os.makedirs(a.out, exist_ok=True)
    dest = os.path.join(a.out, "%s-%s.json" % (now.strftime("%Y%m%dT%H%M%SZ"), rid))
    with open(dest, "w") as f:
        json.dump(record, f, indent=1)

    print("%d rounds x %d hands, %s seeds, %d opponents; incumbent %s: %+.1f bb/100"
          % (len(seeds), a.hands, "held-out" if a.final else "development", len(pool_paths), bots[0]["path"],
             bots[0]["bb100"]))
    for b in bots[1:]:
        print("%-32s %+9.1f bb/100, paired diff %+.1f ± %s bb/100, errors %d, timeouts %d, bank-outs %d, "
              "worst round %.2f s" % (b["path"], b["bb100"], b["diff_bb100"],
                                      "%.1f" % b["se_bb100"] if b["se_bb100"] is not None else "?",
                                      b["errors"], b["timeouts"], b["bank_outs"], b["worst_round_think_s"]))
    print("wrote", dest)


if __name__ == "__main__":
    main()
