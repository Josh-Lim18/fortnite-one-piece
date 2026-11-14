"""analyze.py must read back the known habits of a calling station, the shover and the nit from recorded
hands, its clones must play like the seats they were fitted to, and every pool bot must act without errors.

    python3 tests/test_analyze.py [--kit PATH]
"""
import argparse
import contextlib
import glob
import importlib.util
import io
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OPPONENTS = os.path.join(ROOT, "evaluation", "opponents")
sys.path.insert(0, os.path.join(ROOT, "evaluation"))
import run  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--kit", default=os.path.join(ROOT, "kit"))
KIT = run.use_kit(ap.parse_args().kit)
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402
import analyze  # noqa: E402
from clone_base import PCT  # noqa: E402


def agent(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Agent


def record(agents, path, hands, us=0):
    """Play a table and save it as the site does: chips won per seat, other seats' cards only at showdown."""
    players = [LocalPlayer(a) for a in agents]
    log = FixedHandsTable(players, hands=hands, seed=3, record=True).play()["log"]
    errors = [p.stats.error_samples[0] for p in players if p.stats.errors]
    assert not errors, errors[0]
    slowest = max(p.stats.as_dict()["avg_ms"] for p in players)
    assert slowest < 1.0, "a bot averages %.2f ms a decision" % slowest
    saved = [{"n": h["n"], "button": h["button"], "bb": h["bb"], "events": h["events"],
              "results": [e - s for s, e in zip(h["stacks"], h["end"])],
              "hole": {s: c for s, c in h["hole"].items() if int(s) == us or s in h.get("showdown", {})}}
             for h in log]
    with open(path, "w") as f:
        json.dump({"hands": saved, "round": {"ref": os.path.basename(path)[:-5]}}, f)


def rates(path):
    rnd = analyze.load_hands(path)
    seats, rows = analyze.analyse(rnd)
    return rnd, seats, rows, [{k: s["c"][k] / max(s["c"][of], 1) for k, of in analyze.RATES.items()} for s in seats]


station = agent(os.path.join(KIT, "examples", "calling_station.py"))
shover = agent(os.path.join(OPPONENTS, "shover.py"))
nit = agent(os.path.join(OPPONENTS, "nit.py"))

with tempfile.TemporaryDirectory() as tmp:
    # Known bots: the rates must land where their behaviour puts them.
    known = os.path.join(tmp, "known.json")
    record([station, shover, nit], known, hands=3000)
    rnd, seats, rows, r = rates(known)
    assert rnd["seat"] == 0, "our seat should be inferred as the one whose cards are always present"
    assert r[0]["pfr"] == r[0]["bet"] == r[0]["raise"] == r[0]["fold_to_bet"] == 0 and r[0]["vpip"] > 0.6, r[0]
    assert 0.17 < r[1]["shove"] < 0.23 and r[1]["pfr"] == r[1]["shove"], r[1]
    assert r[2]["vpip"] < 0.08 and r[2]["shove"] < 0.03, r[2]
    assert seats[1]["shown"] and all(PCT[h] <= 0.20 for h in seats[1]["shown"]), seats[1]["shown"]
    assert sum(row["chips"] for row in rows) == seats[0]["c"]["chips"] and len(rows) == 3000

    # The whole report prints, and --emit writes a loadable clone for each opponent seat only.
    out = io.StringIO()
    sys.argv = ["analyze.py", tmp, "--emit", os.path.join(tmp, "clones")]
    with contextlib.redirect_stdout(out):
        analyze.main()
    assert "ten biggest losing hands" in out.getvalue() and "by position" in out.getvalue(), out.getvalue()
    clones = sorted(glob.glob(os.path.join(tmp, "clones", "*.py")))
    assert [os.path.basename(c) for c in clones] == ["clone_known_1.py", "clone_known_2.py"], clones
    cloned = [station] + [agent(c) for c in clones]

    # Clones of the shover and the nit, back at the same table, show the rates they were fitted to.
    again = os.path.join(tmp, "again.json")
    record(cloned, again, hands=3000)
    c = rates(again)[3]
    assert abs(c[1]["shove"] - r[1]["shove"]) < 0.04 and abs(c[2]["vpip"] - r[2]["vpip"]) < 0.04, (c[1], c[2])

    # Every bot in the pool plays a full table with no errors, well under 1 ms a decision.
    pool = [agent(os.path.join(OPPONENTS, name + ".py"))
            for name in ("starter", "maniac", "nit", "shover", "equity_tag", "trapper", "clone_base")]
    record(pool + [station], os.path.join(tmp, "pool.json"), hands=1000)
    rates(os.path.join(tmp, "pool.json"))

print("analyze ok: station vpip %.0f%% pfr 0, shover shove %.1f%% (clone %.1f%%), nit vpip %.1f%% (clone %.1f%%), "
      "pool of %d plays clean" % (100 * r[0]["vpip"], 100 * r[1]["shove"], 100 * c[1]["shove"],
                                  100 * r[2]["vpip"], 100 * c[2]["vpip"], len(pool)))
