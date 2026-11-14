"""Opponent decisions from hand files, one row per decision; also simulates labelled round files to fit on.

    python3 model/dataset.py --simulate 160 --seed 1 --out model/sim   # record tables of known bots
    python3 model/dataset.py model/sim                                  # row counts of a folder of round files

Round files have the shape kit/fetch_hands.py saves and tools/analyze.py's load_hands reads; simulated ones also
carry "bots", the file each seat played, and keep hole cards only for seats that reached showdown, as the site does.
"""
import argparse
import glob
import hashlib
import json
import multiprocessing
import os
import random
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze import load_hands, position  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402
from profiler import STREETS, cell, decisions, showdown_buckets  # noqa: E402
import sim  # noqa: E402

FIT_SAMPLES = 150  # random hands each showdown hand is ranked against when building rows
HOLD_OUT = 4       # every fourth round file (sorted by name) is held out for evaluation


def pool():
    """Every known bot file with an Agent: kit/examples, kit/bot.py, opponents/."""
    files = sorted(glob.glob(os.path.join(ROOT, "kit/examples/*.py")) + [os.path.join(ROOT, "kit/bot.py")]
                   + glob.glob(os.path.join(ROOT, "opponents/*.py")))
    return [os.path.relpath(f, ROOT) for f in files if re.search(r"^(class Agent\b|Agent = )", open(f).read(), re.M)]


def record(bots, seed, path, hands=1000):
    """Play one table of the given bot files (paths from the repo root) and save it as a labelled round file."""
    rng = random.Random(seed)
    random.seed(rng.randrange(1 << 30))
    players = [LocalPlayer(sim._seeded(sim.load(os.path.join(ROOT, b)), rng.randrange(1 << 30))) for b in bots]
    log = FixedHandsTable(players, hands=hands, seed=rng.randrange(1 << 30), record=True).play()["log"]
    for h in log:  # the site shows other seats' cards only at showdown; "dealt" keeps all for fitting ranges
        h["dealt"] = h["hole"]
        h["hole"] = {s: c for s, c in h["hole"].items() if s in h.get("showdown", {})}
    with open(path, "w") as f:
        json.dump({"round": {"ref": os.path.splitext(os.path.basename(path))[0]}, "bots": bots, "hands": log}, f)
    return path


def _simulate(job):
    r, seed, out = job
    rng = random.Random(seed * 1000003 + r)
    bots = [rng.choice(pool()) for _ in range(rng.choice((7, 8)))]
    return record(bots, rng.randrange(1 << 30), os.path.join(out, "sim_%d_%03d.json" % (seed, r)))


def simulate(rounds, seed, out):
    os.makedirs(out, exist_ok=True)
    with multiprocessing.Pool() as p:
        return p.map(_simulate, [(r, seed, out) for r in range(rounds)])


def load(path):
    """(round from load_hands, label per seat). Simulated rounds label every seat by its bot file and every seat is
    an opponent; real rounds label each rival seat "team <hash>", so fitted.py names no team, and ours None."""
    rnd = load_hands(path)
    with open(path) as f:
        data = json.load(f)
    bots = data.get("bots")
    if bots:
        rnd["seat"] = None
    elif rnd["players"]:
        bots = [None if i == rnd["seat"] else "team " + hashlib.md5(p.encode()).hexdigest()[:6]
                for i, p in enumerate(rnd["players"])]
    for h, raw in zip(rnd["hands"], data["hands"]):
        h["dealt"] = {int(s): c for s, c in (raw.get("dealt") or {}).items()}
    return rnd, bots


def summaries(rnd):
    """Each hand as the on_hand_end summary a bot sees: hand_number, button, history, board, shown."""
    for h in rnd["hands"]:
        n = len(h["results"])
        street, history, board, folded = "preflop", [], [], set()
        for ev in h["events"]:
            if ev[0] == "post":
                history.append({"seat": ev[1], "street": "preflop", "amount": ev[2],
                                "action": "big_blind" if history else "small_blind"})
            elif ev[0] == "board":
                street, board = ev[1], ev[2]
            elif ev[0] == "act":
                history.append({"seat": ev[1], "street": street, "action": ev[2], "amount": ev[3]})
                if ev[2] == "fold":
                    folded.add(ev[1])
        live = [s for s in range(n) if s not in folded]
        shown = {str(s): h["hole"][s] for s in live if s in h["hole"]} if len(live) > 1 else {}
        yield {"hand_number": h["n"], "button": h["button"], "seats": n, "history": history,
               "board": board, "shown": shown, "dealt": h.get("dealt") or {}}


def rows(path, samples=FIT_SAMPLES, showdown_only=False):
    """One dict per opponent decision in a round file. hole, board and strength (the hand's bucket on that
    street, 0 weakest) are set when the seat's cards are known: every hand in simulated files (unless
    `showdown_only`), only hands that reached showdown in real ones."""
    rnd, bots = load(path)
    out = []
    for s in summaries(rnd):
        shown = {int(k): v for k, v in s["shown"].items()}
        if s["dealt"] and not showdown_only:
            acted = {seat for seat, _, _, _, _, a in decisions(s["history"], s["seats"]) if a}
            shown = {seat: c for seat, c in s["dealt"].items() if seat in acted}
        strength = showdown_buckets(shown, s["board"], random.Random(s["hand_number"]), samples) if shown else {}
        for seat, street, size, raises, players, action in decisions(s["history"], s["seats"]):
            if seat == rnd["seat"]:
                continue
            sd = seat in shown and street < len(strength[seat])
            out.append({"round": rnd["ref"], "seat": seat, "bot": bots[seat] if bots else None,
                        "hand": s["hand_number"], "street": STREETS[street],
                        "position": position(seat, s["button"], s["seats"]), "players": players,
                        "faces_bet": size > 0, "size": size, "raises": raises, "action": action,
                        "cell": cell(street, size, raises),
                        "hole": shown[seat] if sd else None, "board": s["board"] if sd else None,
                        "strength": strength[seat][street] if sd else None,
                        "dealt": bool(s["dealt"]) and not showdown_only})
    return out


def _count(path):
    return len(rows(path))


def split(folder):
    """(train, held-out) round files of a folder, split by round."""
    files = sorted(glob.glob(os.path.join(folder, "*.json")))
    if not files:
        raise SystemExit("no .json round files in %s" % folder)
    return ([f for i, f in enumerate(files) if i % HOLD_OUT != HOLD_OUT - 1],
            [f for i, f in enumerate(files) if i % HOLD_OUT == HOLD_OUT - 1])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folder", nargs="?", help="round files to summarise")
    ap.add_argument("--simulate", type=int, metavar="ROUNDS", help="write this many simulated 1,000-hand rounds")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(ROOT, "model/sim"))
    a = ap.parse_args()
    if a.simulate:
        print("wrote %d round files to %s from a pool of %d bots" % (len(simulate(a.simulate, a.seed, a.out)),
                                                                     a.out, len(pool())))
    if a.folder:
        train, test = split(a.folder)
        with multiprocessing.Pool() as p:
            counts = p.map(_count, train + test)
        print("%d rounds (%d train, %d held out), %d opponent decisions" % (len(counts), len(train), len(test), sum(counts)))
        r = rows((train + test)[0])
        print("first row:", r[0], "\nfirst showdown row:", next((x for x in r if x["hole"]), None))


if __name__ == "__main__":
    main()
