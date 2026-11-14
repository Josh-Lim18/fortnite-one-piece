"""What paired comparisons rely on: repeatable deals, zero-sum tables, and a bot compared with itself
scoring exactly zero.

    python3 tests/test_run.py [--kit PATH]
"""
import argparse
import glob
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "evaluation"))
import aggregate  # noqa: E402
import run  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--kit", default=os.path.join(REPO, "kit"))
KIT = run.use_kit(ap.parse_args().kit)
EX = os.path.join(KIT, "examples")
POOL = [run.load(os.path.join(EX, f)) for f in sorted(os.listdir(EX)) if f.endswith(".py")]


def table():
    return [POOL[i % len(POOL)] for i in range(run.SEATS)]


def test_same_seed_same_chips():
    assert run.play(table(), 60, 5)[0] == run.play(table(), 60, 5)[0]


def test_zero_sum():
    assert sum(run.play(table(), 60, 3)[0]) == 0


def test_self_compare_is_zero():
    rounds = run.compare([POOL[0], POOL[0]], POOL, [11, 12, 13, 14], 40)
    s = run.summary(rounds, 1, 40)
    assert s["diff_bb100"] == 0 and s["se_bb100"] == 0, s


def test_aggregate_dedupes_and_needs_holdout():
    def record(final, diffs):
        rounds = [{"seed": 100 + i, "seat": i % run.SEATS} for i in range(len(diffs))]
        return {"final": final, "engine_revision": "e", "settings": {"hands": 1000},
                "incumbent": {"path": "inc.py", "sha256": "i"}, "opponents": [{"path": "o.py", "sha256": "o"}],
                "candidates": [{"path": "cand.py", "sha256": "c", "round_diffs": diffs}], "rounds": rounds}
    with tempfile.TemporaryDirectory() as tmp:
        for name, rec in (("a", record(True, [10, 12, 11, 9])), ("b", record(True, [10, 12, 11, 9])),
                          ("c", record(False, [10, 12, 11, 9]))):
            with open(os.path.join(tmp, name + ".json"), "w") as f:
                json.dump(rec, f)
        rows = list(aggregate.collect(sorted(glob.glob(os.path.join(tmp, "*.json"))))["i"]["rows"].values())
    final = [r for r in rows if r["final"]]
    assert len(rows) == 2 and len(final) == 1 and len(final[0]["diffs"]) == 4, rows  # a repeated deal counts once
    m, se = run.mean_se(list(final[0]["diffs"].values()))
    assert aggregate.verdict(True, m, se) == "better"
    assert aggregate.verdict(False, m, se).startswith("keep incumbent")
    assert aggregate.verdict(True, 1.0, 1.0) == "keep incumbent"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
