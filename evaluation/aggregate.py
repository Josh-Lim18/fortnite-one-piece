"""One table per incumbent from every record evaluation/run.py wrote.

    python3 evaluation/aggregate.py [--results evaluation/results]

A candidate is "better" only when, on the held-out seeds, its paired difference is above twice its
standard error. Anything else keeps the incumbent. Rounds are pooled across records only when the
engine, opponent pool and hands per round match; a repeated (seed, seat) is the same deal and counts once.
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from run import mean_se  # noqa: E402


def collect(paths):
    """{incumbent sha: {"path", "rows": {row key: {"path", "final", "pool", "hands", "diffs": {(seed, seat): d}}}}}"""
    tables = {}
    for path in paths:
        with open(path) as f:
            rec = json.load(f)
        inc = rec["incumbent"]
        pool = "".join(sorted(o["sha256"] for o in rec["opponents"]))
        hands = rec["settings"]["hands"]
        t = tables.setdefault(inc["sha256"], {"path": inc["path"], "rows": {}})
        for c in rec["candidates"]:
            key = (c["sha256"], rec["final"], rec["engine_revision"], pool, hands)
            row = t["rows"].setdefault(key, {"path": c["path"], "sha": c["sha256"], "final": rec["final"],
                                             "engine": rec["engine_revision"], "pool": len(rec["opponents"]),
                                             "hands": hands, "diffs": {}})
            for rd, d in zip(rec["rounds"], c["round_diffs"]):
                row["diffs"][(rd["seed"], rd["seat"])] = d
    return tables


def verdict(final, m, se):
    if not final:
        return "keep incumbent (development seeds; run --final)"
    return "better" if se is not None and m > 2 * se else "keep incumbent"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", default=os.path.join(HERE, "results"))
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(a.results, "*.json")))
    if not paths:
        sys.exit("No records in %s: run evaluation/run.py first." % a.results)
    for sha, t in collect(paths).items():
        print("\n== incumbent %s (%s) ==" % (t["path"], sha[:8]))
        print("%-34s %-9s %6s %6s %5s %8s %22s  %s" % ("candidate", "seeds", "rounds", "hands", "pool", "engine",
                                                     "diff bb/100 ± se", "verdict"))
        for row in sorted(t["rows"].values(), key=lambda r: (r["path"], not r["final"])):
            m, se = mean_se(list(row["diffs"].values()))
            print("%-34s %-9s %6d %6d %5d %8s %22s  %s" % (
                "%s (%s)" % (row["path"], row["sha"][:8]), "held-out" if row["final"] else "dev",
                len(row["diffs"]), row["hands"], row["pool"], row["engine"][:8],
                "%+.1f ± %s" % (m, "?" if se is None else "%.1f" % se), verdict(row["final"], m, se)))
    print("\nbetter = held-out seeds and difference > 2 standard errors; otherwise keep the incumbent.")


if __name__ == "__main__":
    main()
