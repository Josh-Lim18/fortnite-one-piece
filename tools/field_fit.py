"""Calibrate one opponents/field/ clone per real team, and check the pool against what really happened.

    python3 tools/field_fit.py fit HANDS_GLOB [--from 24 --to 46 --iters 8 --seeds 2]   # writes opponents/field/clone_*.py
    python3 tools/field_fit.py validate HANDS_GLOB [--from 24 --to 45 --seeds 8 --hero notes/bot-v1-fast.py]

Both replay the real tables: every seat of every real round in its file's order, each team played by its clone,
our seat by the hero bot. fit nudges each clone's profile until its stats in those replays match the team's real
ones; validate compares the hero's and every team's bb/100 in the replays with the real results.
"""
import argparse
import json
import math
import multiprocessing
import os
import random
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "opponents", "field"))
import field_stats as fs  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402
from field_base import DEFAULT, POSITIONS, make_agent  # noqa: E402
from sim import load  # noqa: E402

ME = "Joca"
OUT = os.path.join(ROOT, "opponents", "field")
PRIOR = 30     # a target rate is pulled toward the field's by this many opportunities
WORKERS = 6    # the laptop is shared
_JOB = {}      # state handed to forked workers: agent factories are closures, not picklable
CLONE = '''"""Field clone of team %s: tools/field_fit.py calibrated it to %d real hands (rounds r%03d-r%03d)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from field_base import make_agent  # noqa: E402

Agent = make_agent(%s)
'''
# (profile key, target rate, gain, low, high): key += gain * (target - simulated), clamped.
STEPS = ([("open_" + p, "pfr_" + p, 1.3, 0.0, 1.0) for p in POSITIONS[:5]] + [
    ("open_BB", "pfr_BB", 1.5, 0.0, 1.0),
    ("limp", "limp", 1.0, 0.0, 1.0),
    ("threebet", "threebet", 1.0, 0.0, 1.0),
    ("call_open", "call_open", 1.0, 0.0, 1.0),
    ("call_allin", "call_allin", 1.0, 0.0, 1.0),
    ("shove", "shove", 1.0, 0.0, 1.0),
    ("cbluff", "cbet", 1.2, 0.0, 1.0),
    ("val_flop", "bet_flop", -0.6, 0.0, 1.0),
    ("val_turn", "bet_turn", -0.6, 0.0, 1.0),
    ("val_river", "bet_river", -0.6, 0.0, 1.0),
    ("call_margin", "fold_to_bet", 0.6, -0.6, 0.8),
    ("raise_eq", "raise_bet", -0.8, 0.2, 1.0),
])


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def tables(rounds):
    """(team per seat, our seat) for each real round."""
    return [(rnd["players"], rnd["seat"]) for rnd, _ in rounds]


def _table(job):
    k, seed = job
    names, ours = _JOB["tables"][k]
    random.seed(seed)
    factories = [_JOB["hero"] if i == ours else _JOB["agents"][n] for i, n in enumerate(names)]
    players = []
    for i, f in enumerate(factories):
        agent = f()
        if hasattr(agent, "rng"):
            agent.rng = random.Random(seed * 1009 + i)
        players.append(LocalPlayer(lambda a=agent: a))
    out = FixedHandsTable(players, hands=_JOB["hands"], seed=seed, record=True).play()
    errors = sum(p.stats.errors for p in players)
    rnd = fs.from_log(out["log"], names, ours)
    return k, [s for s in fs.walk(rnd)], out["chips"], errors


def replay(profiles, hero, tabs, seeds, hands=1000, base=1):
    """Play every table `seeds` times. Returns [(table index, walk seats, chips per seat)] and the bot error count."""
    _JOB.clear()
    _JOB.update(tables=tabs, hero=hero, hands=hands, agents={n: make_agent(p) for n, p in profiles.items()})
    jobs = [(k, base * 7919 + k * 101 + s) for k in range(len(tabs)) for s in range(seeds)]
    with multiprocessing.get_context("fork").Pool(WORKERS) as pool:
        res = pool.map(_table, jobs)
    return [(k, seats, chips) for k, seats, chips, _ in res], sum(e for *_, e in res)


def sim_teams(res, tabs):
    return fs.by_team([({"players": tabs[k][0]}, seats) for k, seats, _ in res])


def targets(rounds):
    teams = fs.by_team(rounds)
    prior = fs.field(teams)
    return teams, {n: fs.rates(t, prior, PRIOR) for n, t in teams.items()}, prior


def quantiles(xs, default):
    if len(xs) < 10:
        return default
    xs = sorted(xs)
    return tuple(round(xs[int(q * (len(xs) - 1))], 2) for q in (0.1, 0.3, 0.5, 0.7, 0.9))


def initial(team, t, real):
    p = dict(DEFAULT)
    for key, rate, *_ in STEPS:
        if key.startswith("open_") or key in ("limp", "threebet", "call_open", "call_allin", "shove"):
            p[key] = min(1.0, t[rate] * (1.3 if key.startswith("open_") else 1.0))
    for s in fs.STREETS:
        p["sizes_" + s] = quantiles(real["sizes"][s], DEFAULT["sizes_" + s])
    p["call_3bet"] = max(0.0, (1 - t["fold_3bet"]) * t["pfr"] - p["fourbet"])
    return p


def update(p, t, s):
    """One calibration step of profile p toward target rates t from simulated rates s."""
    for key, rate, gain, lo, hi in STEPS:
        if t.get(rate) is not None and s.get(rate) is not None:
            p[key] = round(min(hi, max(lo, p[key] + gain * (t[rate] - s[rate]))), 4)
    if s["fold_3bet"] is not None:
        p["call_3bet"] = round(max(0.0, p["call_3bet"] + (s["fold_3bet"] - t["fold_3bet"]) * t["pfr"]), 4)
    gap = lambda r: r["fold_pot"] - r["fold_small"]  # noqa: E731
    if s["fold_pot"] is not None and s["fold_small"] is not None:
        p["call_slope"] = round(min(3.0, max(0.0, p["call_slope"] + 1.5 * (gap(t) - gap(s)))), 4)


CHECK = ("vpip", "pfr", "threebet", "fold_3bet", "call_allin", "cbet", "bet_flop", "bet_turn", "bet_river",
         "fold_to_bet", "fold_small", "fold_medium", "fold_pot", "raise_bet", "wtsd", "big_strong")


def calibration(names, real, sim):
    """Markdown: real / simulated per stat (percent; af as a ratio), and the worst VPIP/PFR/fold-to-bet miss."""
    print("| team | hands | " + " | ".join(CHECK) + " | af |")
    print("|" + "---|" * (len(CHECK) + 3))
    for n in names:
        r, s = real[n], sim[n]
        cells = ["%s / %s" % (fs.pct(r[k]), fs.pct(s[k])) for k in CHECK]
        af = "%.2f / %.2f" % (r["af"] or 0, s["af"] or 0)
        print("| %s | %d | %s | %s |" % (n, r["hands"], " | ".join(cells), af))


def misses(names, real, sim):
    """Per team: points off on VPIP, PFR and fold-to-bet, and the AF ratio."""
    out = {}
    for n in names:
        r, s = real[n], sim[n]
        out[n] = {k: 100 * abs(r[k] - s[k]) for k in ("vpip", "pfr", "fold_to_bet")}
        out[n]["af"] = s["af"] / r["af"] if r["af"] and s["af"] else None
    return out


def fit(a):
    rounds = fs.load_rounds(a.hands, a.first, a.last)
    teams, tgt, _ = targets(rounds)
    raw = {n: fs.rates(t) for n, t in teams.items()}
    names = sorted(n for n in teams if n != ME)
    profiles = {n: initial(n, tgt[n], teams[n]) for n in names}
    hero, tabs = load(a.hero), tables(rounds)
    for it in range(a.iters):
        res, errors = replay(profiles, hero, tabs, a.seeds, base=it + 1)
        sim = {n: fs.rates(t) for n, t in sim_teams(res, tabs).items()}
        m = misses(names, raw, sim)
        worst = {k: max(v[k] for v in m.values()) for k in ("vpip", "pfr", "fold_to_bet")}
        print("iteration %d: worst miss vpip %.1f, pfr %.1f, fold-to-bet %.1f points; %d teams within 3/3/3; "
              "bot errors %d" % (it, worst["vpip"], worst["pfr"], worst["fold_to_bet"],
                                 sum(1 for v in m.values() if max(v["vpip"], v["pfr"], v["fold_to_bet"]) <= 3), errors),
              flush=True)
        if it < a.iters - 1:
            for n in names:
                update(profiles[n], tgt[n], sim[n])
    calibration(names, raw, sim)
    for n in names:
        with open(os.path.join(OUT, "clone_%s.py" % slug(n)), "w") as f:
            f.write(CLONE % (n, teams[n]["c"]["hands"], a.first, min(a.last, max(int(r["ref"][-3:]) for r, _ in rounds)),
                             json.dumps(profiles[n], indent=4, ensure_ascii=False).replace("[", "(").replace("]", ")")))
    print("wrote %d clones to %s" % (len(names), OUT))


def _mean_se(xs):
    m = statistics.mean(xs)
    return m, (statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else float("inf"))


def validate(a):
    rounds = fs.load_rounds(a.hands, a.first, a.last)
    rounds = [(r, s) for r, s in rounds if r["players"][r["seat"]] == ME]
    tabs = tables(rounds)
    profiles = {}
    for n in {n for names, _ in tabs for n in names if n != ME}:
        path = os.path.join(OUT, "clone_%s.py" % slug(n))
        if not os.path.exists(path):
            raise SystemExit("no clone for %s at %s: run fit first" % (n, path))
        profiles[n] = load(path).profile
    res, errors = replay(profiles, load(a.hero), tabs, a.seeds, base=1000)
    real_hero, sim_hero = [], [[] for _ in tabs]
    team_real, team_sim = {}, {}
    for k, (rnd, seats) in enumerate(rounds):
        real_hero.append(100.0 * seats[rnd["seat"]]["c"]["won_bb"] / len(rnd["hands"]))
        for i, n in enumerate(rnd["players"]):
            team_real.setdefault(n, []).append(100.0 * seats[i]["c"]["won_bb"] / len(rnd["hands"]))
    per_table = {}
    for k, seats, chips in res:
        per_table.setdefault(k, []).append([c / 20.0 / 10.0 for c in chips])  # chips -> bb/100 over 1,000 hands
    for k, runs in per_table.items():
        names, ours = tabs[k]
        sim_hero[k] = statistics.mean(r[ours] for r in runs)
        for i, n in enumerate(names):
            team_sim.setdefault(n, []).append(statistics.mean(r[i] for r in runs))
    print("hero %s, %d real rounds, %d seeds each, bot errors %d" % (a.hero, len(tabs), a.seeds, errors))
    print("\n| round | table | real bb/100 | predicted |")
    print("|---|---|---|---|")
    for k, (rnd, _) in enumerate(rounds):
        print("| %s | %d seats | %+.1f | %+.1f |" % (rnd["ref"], len(rnd["players"]), real_hero[k], sim_hero[k]))
    rm, rse = _mean_se(real_hero)
    pm, pse = _mean_se(sim_hero)
    print("| **mean** | | **%+.1f ± %.1f** | **%+.1f ± %.1f** |" % (rm, rse, pm, pse))
    r = statistics.correlation(real_hero, sim_hero) if len(tabs) > 2 else float("nan")
    print("\nper-round correlation real vs predicted: %.2f" % r)
    real_t = fs.by_team(rounds)
    sim_t = sim_teams(res, tabs)
    print("\nhero stats, real / simulated:")
    hr, hs = fs.rates(real_t[ME]), fs.rates(sim_t[ME])
    for key in ("vpip", "pfr", "threebet", "call_allin", "cbet", "bet_flop", "fold_to_bet", "wtsd", "af",
                "bb100", "sd_bb100", "nosd_bb100"):
        print("  %-12s %8.2f %8.2f" % (key, hr[key] or 0, hs[key] or 0))
    print("\n| team | rounds | real bb/100 | predicted | real rank | predicted rank |")
    print("|---|---|---|---|---|---|")
    order_r = sorted(team_real, key=lambda n: -statistics.mean(team_real[n]))
    order_s = sorted(team_sim, key=lambda n: -statistics.mean(team_sim[n]))
    for n in order_r:
        print("| %s | %d | %+.0f | %+.0f | %d | %d |" % (n, len(team_real[n]), statistics.mean(team_real[n]),
                                                     statistics.mean(team_sim[n]), order_r.index(n) + 1,
                                                     order_s.index(n) + 1))
    xs = [statistics.mean(team_real[n]) for n in order_r]
    ys = [statistics.mean(team_sim[n]) for n in order_r]
    print("\nteam correlation real vs predicted bb/100: %.2f (Pearson), %.2f (rank)" % (
        statistics.correlation(xs, ys), statistics.correlation([order_r.index(n) for n in order_r],
                                                               [order_s.index(n) for n in order_r])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=("fit", "validate"))
    ap.add_argument("hands", help="round files, e.g. ~/Downloads/poker-v1/hands/'saturday_r0*.json'")
    ap.add_argument("--from", dest="first", type=int, default=24)
    ap.add_argument("--to", dest="last", type=int, default=46)
    ap.add_argument("--iters", type=int, default=8)
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--hero", default=os.path.join(ROOT, "notes", "bot-v1-fast.py"))
    a = ap.parse_args()
    fit(a) if a.mode == "fit" else validate(a)


if __name__ == "__main__":
    main()
