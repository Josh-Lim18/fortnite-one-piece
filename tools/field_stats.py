"""Per-team statistics from hand files: the targets a field clone is calibrated to.

    python3 tools/field_stats.py ~/Downloads/poker-v1/hands/'saturday_r0*.json' [--from 24] [--min-hands 2000]

Works on the site's round files and on simulated rounds (from_log), so real and simulated stats come from one walker.
"""
import argparse
import glob
import os
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opponents"))
from analyze import load_hands, position  # noqa: E402
from clone_base import strength  # noqa: E402

SHOVE = 800        # chips: a preflop raise to this much is a shove, a call of this much a call of a shove
BIG = 0.75         # a postflop bet or raise of this share of the pot counts as big
POSITIONS = ("EP", "MP", "CO", "BTN", "SB", "BB")
STREETS = ("flop", "turn", "river")
# Postflop bet faced, as a share of the pot before it.
BUCKETS = ((0.4, "small"), (0.8, "medium"), (1.25, "pot"), (float("inf"), "over"))
# Rate name -> (count, opportunities); the stats a clone is tuned to and the report prints.
RATES = {
    "vpip": ("vpip", "hands"), "pfr": ("pfr", "hands"), "limp": ("limp", "unraised"),
    "threebet": ("threebet", "faced_open"), "call_open": ("call_open", "faced_open"), "fold_3bet": ("fold_3bet", "faced_3bet"),
    "call_allin": ("call_allin", "faced_allin"), "shove": ("shove", "hands"), "cbet": ("cbet", "cbet_opp"),
    "fold_to_bet": ("fold", "faced_bet"), "raise_bet": ("raise_bet", "faced_bet"), "wtsd": ("showdown", "saw_flop"),
    "big_bets": ("big", "sized"), "big_strong": ("big_sd_strong", "big_sd"), "small_strong": ("small_sd_strong", "small_sd"),
    **{"%s_%s" % (k, p): ("%s_%s" % (k, p), "hands_" + p) for p in POSITIONS for k in ("vpip", "pfr")},
    **{"bet_" + s: ("bet_" + s, "checked_to_" + s) for s in STREETS},
    **{"raise_" + s: ("raise_" + s, "faced_bet_" + s) for s in STREETS},
    **{"fold_" + s: ("fold_" + s, "faced_bet_" + s) for s in STREETS},
    **{"fold_" + b: ("fold_" + b, "faced_" + b) for _, b in BUCKETS},
}


def walk(rnd):
    """Counts per seat for one round in load_hands' shape. Returns a list, one {"c": Counter, "sizes": {street: [pot
    shares]}} per seat."""
    n = len(rnd["hands"][0]["results"])
    seats = [{"c": Counter(), "sizes": {s: [] for s in STREETS}} for _ in range(n)]
    for h in rnd["hands"]:
        bets, earlier, pot, street, raises = [0] * n, [0] * n, 0, "preflop", 0
        folded, entered, raised, opener, aggressor, board = set(), set(), set(), None, None, []
        faced_3bet, cbet_seen, big, small, shoved, flop = set(), False, set(), set(), set(), set()
        for ev in h["events"]:
            kind, seat = ev[0], ev[1]
            if kind == "post":
                bets[seat] += ev[2]
                pot += ev[2]
            elif kind == "board":
                earlier = [e + b for e, b in zip(earlier, bets)]
                street, bets, raises, board, cbet_seen = ev[1], [0] * n, 0, ev[2], False
                if street == "flop":
                    flop = set(range(n)) - folded
            elif kind == "refund":
                pot -= ev[2]
            elif kind == "act":
                action, amount = ev[2], ev[3]
                c, top = seats[seat]["c"], max(bets)
                owed = top - bets[seat]
                if street == "preflop":
                    if top >= SHOVE and owed:
                        c["faced_allin"] += 1
                        c["call_allin"] += action != "fold"
                    if raises == 0:
                        c["unraised"] += 1
                        c["limp"] += action == "call"
                    elif raises == 1 and seat != opener:
                        c["faced_open"] += 1
                        c["threebet"] += action == "raise"
                        c["call_open"] += action == "call"
                    elif seat == opener and seat not in faced_3bet:
                        faced_3bet.add(seat)
                        c["faced_3bet"] += 1
                        c["fold_3bet"] += action == "fold"
                    if action in ("call", "raise"):
                        entered.add(seat)
                    if action == "raise":
                        raised.add(seat)
                        aggressor = seat
                        if raises == 0:
                            opener = seat
                        if amount >= SHOVE:
                            shoved.add(seat)
                elif owed:
                    k = next(b for x, b in BUCKETS if owed <= x * (pot - owed))
                    c["faced_bet"] += 1
                    c["faced_bet_" + street] += 1
                    c["faced_" + k] += 1
                    c["fold"] += action == "fold"
                    c["fold_" + street] += action == "fold"
                    c["fold_" + k] += action == "fold"
                    c["raise_" + street] += action == "raise"
                    c["raise_bet"] += action == "raise"
                else:
                    c["checked_to_" + street] += 1
                    c["bet_" + street] += action == "raise"
                    if street == "flop" and seat == aggressor and not cbet_seen:
                        c["cbet_opp"] += 1
                        c["cbet"] += action == "raise"
                if street == "flop" and not owed:
                    cbet_seen |= seat == aggressor
                if street != "preflop":
                    c["post_aggr"] += action == "raise"
                    c["post_call"] += action == "call"
                    if action == "raise":
                        share = (amount - top) / pot
                        seats[seat]["sizes"][street].append(share)
                        c["sized"] += 1
                        c["big"] += share >= BIG
                        (big if share >= BIG else small).add(seat)
                if action == "raise":
                    pot += amount - bets[seat]
                    bets[seat] = amount
                    raises += 1
                elif action == "call":
                    pot += amount
                    bets[seat] += amount
                elif action == "fold":
                    folded.add(seat)
        showdown = n - len(folded) > 1
        for i, s in enumerate(seats):
            c, pos, won = s["c"], position(i, h["button"], n), h["results"][i] / h["bb"]
            c["hands"] += 1
            c["hands_" + pos] += 1
            c["vpip"] += i in entered
            c["vpip_" + pos] += i in entered
            c["pfr"] += i in raised
            c["pfr_" + pos] += i in raised
            c["won_bb"] += won
            c["won_bb2"] += won * won
            c["shove"] += i in shoved
            c["saw_flop"] += i in flop
            at_sd = showdown and i not in folded
            c["showdown"] += at_sd
            c["sd_bb" if at_sd else "nosd_bb"] += won
            if at_sd and len(board) == 5 and i in h["hole"]:
                made = strength(h["hole"][i], board)[0]
                for tag, flagged in (("big", big), ("small", small)):
                    if i in flagged:
                        c[tag + "_sd"] += 1
                        c[tag + "_sd_strong"] += made >= 2
    return seats


def by_team(rounds):
    """Sum walk() over (round, seats) pairs by team name. Returns {team: {"c", "sizes", "rounds"}}."""
    out = {}
    for rnd, seats in rounds:
        for i, s in enumerate(seats):
            t = out.setdefault(rnd["players"][i], {"c": Counter(), "sizes": {k: [] for k in STREETS}, "rounds": 0})
            t["c"].update(s["c"])  # update keeps negative chip totals; Counter += would drop them
            for k in STREETS:
                t["sizes"][k] += s["sizes"][k]
            t["rounds"] += 1
    return out


def rates(t, prior=None, k=0):
    """A team's rates; with prior (another rates dict) each is pulled toward it by k opportunities."""
    c, out = t["c"], {}
    for name, (num, den) in RATES.items():
        base = prior.get(name) if prior else None
        if base is None:
            out[name] = c[num] / c[den] if c[den] else None
        else:
            out[name] = (c[num] + k * base) / (c[den] + k)
    out["af"] = c["post_aggr"] / c["post_call"] if c["post_call"] else None
    for s in STREETS:
        out["size_" + s] = statistics.median(t["sizes"][s]) if t["sizes"][s] else (prior or {}).get("size_" + s)
    n = c["hands"]
    for k2 in ("won_bb", "sd_bb", "nosd_bb"):
        out[k2.replace("won_bb", "bb100").replace("_bb", "_bb100")] = 100.0 * c[k2] / n if n else None
    out["bb100_se"] = 100.0 * (max(c["won_bb2"] / n - (c["won_bb"] / n) ** 2, 0) / n) ** 0.5 if n else None
    out["hands"] = n
    return out


def field(teams):
    """Rates of every seat pooled: the prior small samples are pulled toward."""
    c, sizes = Counter(), {k: [] for k in STREETS}
    for t in teams.values():
        c.update(t["c"])
        for k in STREETS:
            sizes[k] += t["sizes"][k]
    return rates({"c": c, "sizes": sizes})


def from_log(log, players, seat=None):
    """An engine record (FixedHandsTable(record=True)) in load_hands' shape, hole cards cut to what the site shows."""
    hands = []
    for h in log:
        shown = {int(s) for s in h.get("showdown", {})} | ({seat} if seat is not None else set())
        hands.append({"n": h["n"], "button": h["button"], "bb": h["bb"], "events": h["events"],
                      "results": [e - s for s, e in zip(h["stacks"], h["end"])],
                      "hole": {int(s): c for s, c in h["hole"].items() if int(s) in shown}})
    return {"ref": "sim", "seat": seat, "players": players, "hands": hands}


def load_rounds(pattern, first=0, last=10 ** 9):
    """(round, walk(round)) for each file matching pattern whose round number is in [first, last]."""
    out = []
    for path in sorted(glob.glob(os.path.expanduser(pattern))):
        rnd = load_hands(path)
        if first <= int(rnd["ref"].rsplit("r", 1)[-1]) <= last:
            out.append((rnd, walk(rnd)))
    return out


def pct(x):
    return "-" if x is None else "%.0f" % (100 * x)


COLUMNS = ("vpip", "pfr", "threebet", "fold_3bet", "call_allin", "cbet", "bet_flop", "bet_turn", "bet_river",
           "fold_to_bet", "fold_small", "fold_medium", "fold_pot", "fold_over", "big_bets", "big_strong", "wtsd")


def table(teams, names, extra=None):
    """Markdown rows: rates in percent, then af, sizes and bb/100."""
    print("| team | hands | " + " | ".join(COLUMNS) + " | af | size f/t/r | bb/100 | sd / no-sd |" + (" %s |" % extra[0] if extra else ""))
    print("|" + "---|" * (len(COLUMNS) + 6 + bool(extra)))
    for name in names:
        r = rates(teams[name])
        sizes = "/".join("-" if r["size_" + s] is None else "%.2f" % r["size_" + s] for s in STREETS)
        print("| %s | %d | %s | %s | %s | %+.0f ± %.0f | %+.0f / %+.0f |%s" % (
            name, r["hands"], " | ".join(pct(r[k]) for k in COLUMNS), "-" if r["af"] is None else "%.2f" % r["af"],
            sizes, r["bb100"], r["bb100_se"], r["sd_bb100"], r["nosd_bb100"],
            " %s |" % extra[1](name) if extra else ""))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", help="round files, e.g. ~/Downloads/poker-v1/hands/'saturday_r0*.json'")
    ap.add_argument("--from", dest="first", type=int, default=0, help="first round number to read")
    ap.add_argument("--to", dest="last", type=int, default=10 ** 9, help="last round number to read")
    ap.add_argument("--min-hands", type=int, default=0)
    a = ap.parse_args()
    rounds = load_rounds(a.pattern, a.first, a.last)
    if not rounds:
        raise SystemExit("no round files match %s" % a.pattern)
    teams = by_team(rounds)
    names = sorted((n for n, t in teams.items() if t["c"]["hands"] >= a.min_hands),
                   key=lambda n: -rates(teams[n])["bb100"])
    print("%d rounds, %d teams. Rates in percent; af = postflop bets and raises / calls; sizes are median bet or raise"
          " as a share of the pot." % (len(rounds), len(teams)))
    table(teams, names)


if __name__ == "__main__":
    main()
