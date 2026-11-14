"""Per-seat and per-team statistics and a leak report from the hand histories kit/fetch_hands.py saves.

    python3 tools/analyze.py hands/                          # stats per round and seat, leaks for our seat
    python3 tools/analyze.py hands/ --teams                  # one markdown row per team over every round
    python3 tools/analyze.py hands/ --emit opponents/real/   # also write a clone per team with enough decisions
"""
import argparse
import glob
import json
import os
import re
import statistics
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "opponents"))
from clone_base import DEFAULT, hand_name, strength  # noqa: E402

SHOVE = 800      # a preflop raise to at least this many chips counts as a shove
STACK = 2000     # every seat starts every hand with this many chips
PRIOR = 10       # a clone's rate starts from this many decisions of the average player
MIN_DECISIONS = 2000  # a team gets a clone once it made this many decisions
# Rate -> the count it is a share of. Those that are also keys of clone_base.DEFAULT make up a clone's profile.
RATES = {"vpip": "hands", "pfr": "hands", "shove": "hands", "open": "unraised", "limp": "unraised",
         "reraise": "faced_raise", "call_raise": "faced_raise",
         "bet": "checked_to", "raise": "faced_bet", "fold_to_bet": "faced_bet"}
LAST = {"fold": "folded", "call": "called", "raise": "raised", "check": "checked"}
# Postflop bet faced, as a share of the pot before it; the last bucket is any call of SHOVE chips or more.
SIZES = ((0.4, "<=0.4"), (0.8, "<=0.8"), (1.25, "<=1.25"), (float("inf"), "over"))
STACKOFF = "800+"
CLONE = '''"""Clone of team %s, fitted by tools/analyze.py from %d hands over %d rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent(%r)
'''


def load_hands(path):
    """Read one round file in the site's format (kit/fetch_hands.py; simulated files may lack seat and players).

    Returns {"ref", "seat" (ours, None in simulated files), "players" (team per seat, or None), "hands"};
    each hand is {"n", "button", "bb", "events", "results": [chips won per seat], "hole": {seat: [two cards]}},
    hole holding our cards and those shown at showdown.
    """
    with open(path) as f:
        data = json.load(f)
    try:
        rd = data.get("round") or {}
        hands = []
        for k, h in enumerate(data["hands"]):
            results = h.get("results")
            if results is None:  # the engine's own record has stacks before and after instead
                results = [e - s for s, e in zip(h["stacks"], h["end"])]
            if sum(results):
                raise ValueError("hand %d: results sum to %d, expected chips won per seat summing to 0"
                                 % (k, sum(results)))
            hands.append({"n": h.get("n", k + 1), "button": h["button"], "bb": h.get("bb", 20),
                          "events": h["events"], "results": results,
                          "hole": {int(s): c for s, c in (h.get("hole") or {}).items() if c}})
        if not hands:
            raise ValueError("no hands")
        players = data.get("players")
        if players is not None and len(players) != len(hands[0]["results"]):
            raise ValueError("%d players named for %d seats" % (len(players), len(hands[0]["results"])))
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        first = (data.get("hands") or [None])[0] if isinstance(data, dict) else None
        raise SystemExit("%s: not the shape load_hands expects (%s: %s)\n  top-level keys: %s\n  first hand: %s"
                         % (path, type(e).__name__, e, sorted(data) if isinstance(data, dict) else type(data),
                            sorted(first) if isinstance(first, dict) else first))
    ref = str(rd.get("ref") or os.path.splitext(os.path.basename(path))[0])
    return {"ref": ref, "seat": data.get("seat", rd.get("seat")), "players": players, "hands": hands}


def position(seat, button, n):
    off = (seat - button) % n
    return {n - 1: "CO", 0: "BTN", 1: "SB", 2: "BB"}.get(off, "EP" if off < (n + 2) // 2 else "MP")


def analyse(rnd):
    """Walk one round. Returns (seats, rows): per seat its counts ("c"), first-raise sizes in big blinds
    ("open_bb"), postflop bet sizes as a share of the pot ("bet_pot"), the hands it showed after shoving
    ("shown"), postflop bets faced and folded to by size ("sizes": (bucket, folded) counts) and its made hand
    at showdown by its last action ("sd": (last action, clone_base.strength made class) counts); rows has one
    summary of each hand from our seat, empty when our seat is unknown."""
    n = len(rnd["hands"][0]["results"])
    me = rnd["seat"]
    seats = [{"c": Counter(), "open_bb": [], "bet_pot": [], "shown": Counter(), "sizes": Counter(), "sd": Counter()}
             for _ in range(n)]
    rows = []
    for h in rnd["hands"]:
        bets, pot, street, acted_on, raises, inc = [0] * n, 0, "preflop", "preflop", 0, h["bb"]
        entered, raised, shoved, folded, last, line, board = set(), set(), set(), {}, {}, [], []
        earlier = [0] * n  # chips each seat put in on earlier streets
        for ev in h["events"]:
            kind, seat = ev[0], ev[1]
            if kind == "post":
                bets[seat] += ev[2]
                pot += ev[2]
            elif kind == "board":
                earlier = [e + b for e, b in zip(earlier, bets)]
                street, bets, raises, inc, board = ev[1], [0] * n, 0, h["bb"], ev[2]
                line.append("| " + " ".join(ev[2][-3 if street == "flop" else -1:]))
            elif kind == "act":
                action, amount = ev[2], ev[3]
                c, top = seats[seat]["c"], max(bets)
                last[seat], acted_on = action, street
                line.append("%s %s%s" % ("us" if seat == me else "s%d" % seat, action, " %d" % amount if amount else ""))
                if action == "raise" and earlier[seat] + amount < STACK:  # the starter raises to min_raise_to + pot // 2
                    c["sized"] += 1
                    c["formula"] += amount == top + inc + pot // 2
                if street != "preflop" and top > bets[seat]:
                    owed = top - bets[seat]
                    size = STACKOFF if owed >= SHOVE else next(b for x, b in SIZES if owed <= x * (pot - owed))
                    seats[seat]["sizes"][size, action == "fold"] += 1
                if street == "preflop":
                    if action in ("call", "raise"):
                        entered.add(seat)
                    if raises:
                        c["faced_raise"] += 1
                        c["reraise"] += action == "raise"
                        c["call_raise"] += action == "call"
                    else:
                        c["unraised"] += 1
                        c["open"] += action == "raise"
                        c["limp"] += action == "call"
                    if action == "raise":
                        raised.add(seat)
                        if amount >= SHOVE:
                            shoved.add(seat)
                        elif not raises:
                            seats[seat]["open_bb"].append(amount / h["bb"])
                elif top > bets[seat]:
                    c["faced_bet"] += 1
                    c["fold_to_bet"] += action == "fold"
                    c["raise"] += action == "raise"
                else:
                    c["checked_to"] += 1
                    c["bet"] += action == "raise"
                if action == "raise":
                    if street != "preflop":
                        seats[seat]["bet_pot"].append((amount - top) / pot)
                    inc = max(inc, amount - top)
                    pot += amount - bets[seat]
                    bets[seat] = amount
                    raises += 1
                elif action == "call":
                    pot += amount
                    bets[seat] += amount
                elif action == "fold":
                    folded[seat] = street
        showdown = n - len(folded) > 1
        for i, s in enumerate(seats):
            c = s["c"]
            c["hands"] += 1
            c["vpip"] += i in entered
            c["pfr"] += i in raised
            c["shove"] += i in shoved
            c["showdown"] += showdown and i not in folded
            c["chips"] += h["results"][i]
            c["won_bb"] += h["results"][i] / h["bb"]
            c["won_bb2"] += (h["results"][i] / h["bb"]) ** 2
            if showdown and i in h["hole"] and i not in folded:
                if i in shoved:
                    s["shown"][hand_name(h["hole"][i])] += 1
                if len(board) == 5:
                    s["sd"][LAST[last.get(i, "check")], strength(h["hole"][i], board)[0]] += 1
        if me is not None:
            shown = ["s%d showed %s" % (i, " ".join(c)) for i, c in sorted(h["hole"].items())
                     if i != me and i not in folded]
            rows.append({
                "chips": h["results"][me], "bb": h["bb"],
                "ended": "%s, we folded" % folded[me] if me in folded
                         else acted_on + (" showdown" if showdown else ", they folded"),
                "position": position(me, h["button"], n),
                "last": LAST.get(last.get(me), "no action"),
                "line": "%s #%d %s %s %+d: %s" % (rnd["ref"], h["n"], position(me, h["button"], n),
                                                  " ".join(h["hole"].get(me, ["??"])), h["results"][me],
                                                  ", ".join(line + shown).replace(", |", " |")),
            })
    return seats, rows


def profile(s):
    """A seat's rates as the profile opponents/clone_base.py plays from, each pulled toward the
    average player by PRIOR decisions so a rate seen three times doesn't become a certainty."""
    c = s["c"]
    p = {k: round((c[k] + DEFAULT[k] * PRIOR) / (c[of] + PRIOR), 3) for k, of in RATES.items() if k in DEFAULT}
    for k in ("open_bb", "bet_pot"):
        if s[k]:
            p[k] = round(statistics.median(s[k]), 2)
    return p


def decisions(c):
    return c["unraised"] + c["faced_raise"] + c["checked_to"] + c["faced_bet"]


def teams(rounds):
    """Every seat of every (round, seats) pair summed by team, a seat with no team name standing for itself
    as "<ref> seat <i>". Returns {team: seat dict as analyse makes, plus "rounds" and "ours"}."""
    out = {}
    for rnd, seats in rounds:
        for i, s in enumerate(seats):
            name = rnd["players"][i] if rnd["players"] else "%s seat %d" % (rnd["ref"], i)
            t = out.setdefault(name, {"rounds": 0, "ours": False, **{k: type(v)() for k, v in s.items()}})
            t["rounds"] += 1
            t["ours"] |= i == rnd["seat"]
            for k, v in s.items():
                if isinstance(v, Counter):
                    t[k].update(v)  # Counter += would drop negative chip totals
                else:
                    t[k] += v
    return out


def emit(by_team, out):
    """One clone file per rival team with at least MIN_DECISIONS decisions."""
    os.makedirs(out, exist_ok=True)
    for name, t in sorted(by_team.items()):
        if t["ours"] or decisions(t["c"]) < MIN_DECISIONS:
            continue
        path = os.path.join(out, "clone_%s.py" % re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"))
        with open(path, "w") as f:
            f.write(CLONE % (name, t["c"]["hands"], t["rounds"], profile(t)))
        print("wrote", path)


def share(c, k, of):
    return "%.0f%%" % (100.0 * c[k] / c[of]) if c[of] else "-"


def print_teams(by_team):
    """One markdown row per team, best bb/100 first."""
    print("| team | rounds | hands | decisions | bb/100 ± se | vpip | pfr | 3-bet | shove | postflop aggr |"
          " fold to bet " + " / ".join(b for _, b in SIZES) + " / " + STACKOFF + " pot | open bb | bet pot |"
          " starter size | showdowns after raising: weak / strong | showdowns after calling: weak / strong |")
    print("|" + "---|" * 16)

    def bb100(t):
        return 100.0 * t["c"]["won_bb"] / t["c"]["hands"]

    for name, t in sorted(by_team.items(), key=lambda kv: -bb100(kv[1])):
        c, n = t["c"], t["c"]["hands"]
        se = 100.0 * (max(c["won_bb2"] / n - (c["won_bb"] / n) ** 2, 0) / n) ** 0.5
        folds = " / ".join(share(Counter({"f": t["sizes"][b, True], "n": t["sizes"][b, True] + t["sizes"][b, False]}),
                                 "f", "n") for b in [b for _, b in SIZES] + [STACKOFF])
        aggr = Counter({"a": c["bet"] + c["raise"], "n": c["checked_to"] + c["faced_bet"]})

        def sd(line):  # made class 0-1 (nothing or a pair below top pair) against 2+ (top pair or better)
            weak = t["sd"][line, 0] + t["sd"][line, 1]
            strong = sum(v for (l, m), v in t["sd"].items() if l == line and m >= 2)
            return "%d / %d" % (weak, strong)

        print("| %s%s | %d | %d | %d | %+.0f ± %.0f | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            name, " (us)" if t["ours"] else "", t["rounds"], n, decisions(c), bb100(t), se,
            share(c, "vpip", "hands"), share(c, "pfr", "hands"), share(c, "reraise", "faced_raise"),
            share(c, "shove", "hands"), share(aggr, "a", "n"), folds,
            "%.1f" % statistics.median(t["open_bb"]) if t["open_bb"] else "-",
            "%.2f" % statistics.median(t["bet_pot"]) if t["bet_pot"] else "-",
            share(c, "formula", "sized"), sd("raised"), sd("called")))


def print_round(rnd, seats):
    hands = len(rnd["hands"])
    print("\n== round %s: %d hands, %d seats, our seat %s ==" % (rnd["ref"], hands, len(seats), rnd["seat"]))
    print("seat  hands  vpip   pfr shove   re-raise     bet raise check  call   fold to bet  showdown    chips"
          "  shoved and shown")
    for i, s in enumerate(seats):
        c = s["c"]
        shown = " ".join("%s x%d" % kv if kv[1] > 1 else kv[0] for kv in s["shown"].most_common(12))
        print("%-4s %6d %5s %5s %5s %4s of %-4d %5d %5d %5d %5d  %4s of %-5d %8s %+8d  %s" % (
            "%d%s" % (i, "*" if i == rnd["seat"] else ""), c["hands"], share(c, "vpip", "hands"),
            share(c, "pfr", "hands"), share(c, "shove", "hands"), share(c, "reraise", "faced_raise"),
            c["faced_raise"], c["bet"], c["raise"], c["checked_to"] - c["bet"],
            c["faced_bet"] - c["raise"] - c["fold_to_bet"], share(c, "fold_to_bet", "faced_bet"), c["faced_bet"],
            share(c, "showdown", "hands"), c["chips"], shown))
    print("* is us. re-raise is per preflop decision facing a raise; bet, raise, check, call are postflop counts."
          "\n95%% interval: at most +-%.0f points on a rate over %d hands, +-%.0f points on a rate 'of 50'."
          % (98 / hands ** 0.5, hands, 98 / 50 ** 0.5))


def print_leaks(rows, rounds):
    if len(rows) < 2:
        print("\n== leaks: our seat is unknown, so no leak report ==")
        return
    bbs = [r["chips"] / r["bb"] for r in rows]
    print("\n== leaks: our seat, %d hands in %d rounds: %+d chips, %+.1f +- %.1f bb/100 (one standard error) =="
          % (len(rows), rounds, sum(r["chips"] for r in rows), 100 * statistics.mean(bbs),
             100 * statistics.stdev(bbs) / len(bbs) ** 0.5))
    for title, key in (("street the hand ended on", "ended"), ("position", "position"), ("our last action", "last")):
        print("\nby %-26s hands      won     lost      net" % title)
        groups = {}
        for r in rows:
            groups.setdefault(r[key], []).append(r["chips"])
        for name, chips in sorted(groups.items(), key=lambda kv: sum(kv[1])):
            print("  %-27s %5d %+8d %+8d %+8d" % (name, len(chips), sum(x for x in chips if x > 0),
                                                 sum(x for x in chips if x < 0), sum(chips)))
    print("\nten biggest losing hands")
    for r in sorted(rows, key=lambda r: r["chips"])[:10]:
        if r["chips"] < 0:
            print("  " + r["line"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="a folder of round files, one file, or a glob such as 'hands/saturday_r*.json'")
    ap.add_argument("--teams", action="store_true", help="print one row per team instead of per round and seat")
    ap.add_argument("--emit", metavar="DIR", help="write clone_<team>.py per rival team (use opponents/real/)")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.path, "*.json") if os.path.isdir(a.path) else a.path))
    if not files:
        raise SystemExit("no .json files in %s" % a.path)
    rows, rounds = [], []
    for path in files:
        rnd = load_hands(path)
        seats, round_rows = analyse(rnd)
        if not a.teams:
            print_round(rnd, seats)
        rows += round_rows
        rounds.append((rnd, seats))
    by_team = teams(rounds)
    if a.teams:
        print_teams(by_team)
    else:
        print_leaks(rows, len(files))
    if a.emit:
        emit(by_team, a.emit)


if __name__ == "__main__":
    main()
