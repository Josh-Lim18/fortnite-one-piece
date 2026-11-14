"""analyze.py must read back the known habits of a calling station, the shover and the nit from hands saved in the
site's format, sum each team over rounds whatever its seat, spot the starter's bet-size formula, its clones must play
like the teams they were fitted to, and every pool bot must act without errors."""
import contextlib
import glob
import importlib.util
import io
import json
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OPPONENTS = os.path.join(ROOT, "opponents")
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402
import analyze  # noqa: E402
from clone_base import PCT  # noqa: E402


def agent(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.Agent


def record(agents, names, path, hands, us=0):
    """Play a table and save it as the site does: team names by seat, our seat, chips won per seat, other seats'
    cards only at showdown and hand names under "showdown"."""
    players = [LocalPlayer(a) for a in agents]
    log = FixedHandsTable(players, hands=hands, seed=3, record=True).play()["log"]
    errors = [p.stats.error_samples[0] for p in players if p.stats.errors]
    assert not errors, errors[0]
    slowest = max(p.stats.as_dict()["avg_ms"] for p in players)
    assert slowest < 1.0, "a bot averages %.2f ms a decision" % slowest
    saved = [{"n": h["n"], "button": h["button"], "sb": h["bb"] // 2, "bb": h["bb"], "start_stacks": h["stacks"],
              "hole": {s: c for s, c in h["hole"].items() if int(s) == us or s in h.get("showdown", {})},
              "showdown": h.get("showdown", {}), "board": h["board"], "events": h["events"],
              "results": [e - s for s, e in zip(h["stacks"], h["end"])]}
             for h in log]
    with open(path, "w") as f:
        json.dump({"ref": "r", "seat": us, "players": names, "hands": saved,
                   "round": {"ref": os.path.basename(path)[:-5], "seat": us}}, f)


def rates(path):
    rnd = analyze.load_hands(path)
    seats, rows = analyze.analyse(rnd)
    return rnd, seats, rows, [{k: s["c"][k] / max(s["c"][of], 1) for k, of in analyze.RATES.items()} for s in seats]


station = agent(os.path.join(ROOT, "kit", "examples", "calling_station.py"))
shover = agent(os.path.join(OPPONENTS, "shover.py"))
nit = agent(os.path.join(OPPONENTS, "nit.py"))

with tempfile.TemporaryDirectory() as tmp:
    # Known bots: the rates must land where their behaviour puts them.
    known = os.path.join(tmp, "known.json")
    record([station, shover, nit], ["us", "Shover Team", "nit"], known, hands=3000)
    rnd, seats, rows, r = rates(known)
    assert rnd["seat"] == 0 and rnd["players"] == ["us", "Shover Team", "nit"], (rnd["seat"], rnd["players"])
    assert r[0]["pfr"] == r[0]["bet"] == r[0]["raise"] == r[0]["fold_to_bet"] == 0 and r[0]["vpip"] > 0.6, r[0]
    assert seats[0]["sizes"] and not any(folded for _, folded in seats[0]["sizes"]), seats[0]["sizes"]
    assert 0.17 < r[1]["shove"] < 0.23 and r[1]["pfr"] == r[1]["shove"], r[1]
    assert r[2]["vpip"] < 0.08 and r[2]["shove"] < 0.03, r[2]
    assert seats[1]["shown"] and all(PCT[h] <= 0.20 for h in seats[1]["shown"]), seats[1]["shown"]
    assert sum(row["chips"] for row in rows) == seats[0]["c"]["chips"] and len(rows) == 3000

    # A second round with every team in another seat: teams() sums each team whatever seat it sat in.
    record([nit, station, shover], ["nit", "us", "Shover Team"], os.path.join(tmp, "moved.json"), hands=1000, us=1)
    moved = analyze.load_hands(os.path.join(tmp, "moved.json"))
    by_team = analyze.teams([(rnd, seats), (moved, analyze.analyse(moved)[0])])
    assert by_team["Shover Team"]["rounds"] == 2 and by_team["Shover Team"]["c"]["hands"] == 4000, by_team["Shover Team"]
    assert by_team["us"]["ours"] and not by_team["nit"]["ours"]

    # The whole report prints, and --emit writes a loadable clone for each rival team only.
    out = io.StringIO()
    sys.argv = ["analyze.py", tmp, "--emit", os.path.join(tmp, "clones")]
    with contextlib.redirect_stdout(out):
        analyze.main()
    assert "ten biggest losing hands" in out.getvalue() and "by position" in out.getvalue(), out.getvalue()
    clones = sorted(glob.glob(os.path.join(tmp, "clones", "*.py")))
    assert [os.path.basename(c) for c in clones] == ["clone_nit.py", "clone_shover_team.py"], clones
    sys.argv = ["analyze.py", tmp, "--teams"]
    with contextlib.redirect_stdout(io.StringIO()) as out:
        analyze.main()
    assert "| Shover Team | 2 | 4000 |" in out.getvalue() and "| us (us) |" in out.getvalue(), out.getvalue()
    cloned = [station, agent(clones[1]), agent(clones[0])]

    # Clones of the shover and the nit, back at the same table, show the rates they were fitted to.
    again = os.path.join(tmp, "again.json")
    record(cloned, ["us", "Shover Team", "nit"], again, hands=3000)
    c = rates(again)[3]
    assert abs(c[1]["shove"] - r[1]["shove"]) < 0.04 and abs(c[2]["vpip"] - r[2]["vpip"]) < 0.04, (c[1], c[2])

    # Every bot in the pool plays a full table with no errors, well under 1 ms a decision; the starter's raises all
    # follow its min_raise_to + pot // 2 formula.
    names = ("starter", "maniac", "nit", "shover", "equity_tag", "trapper", "clone_base")
    pool = [agent(os.path.join(OPPONENTS, name + ".py")) for name in names]
    record(pool + [station], list(names) + ["station"], os.path.join(tmp, "pool.json"), hands=1000, us=7)
    starter = rates(os.path.join(tmp, "pool.json"))[1][0]["c"]
    assert starter["sized"] > 50 and starter["formula"] == starter["sized"], starter

print("analyze ok: station vpip %.0f%% pfr 0, shover shove %.1f%% (clone %.1f%%), nit vpip %.1f%% (clone %.1f%%), "
      "pool of %d plays clean" % (100 * r[0]["vpip"], 100 * r[1]["shove"], 100 * c[1]["shove"],
                                  100 * r[2]["vpip"], 100 * c[2]["vpip"], len(pool)))
