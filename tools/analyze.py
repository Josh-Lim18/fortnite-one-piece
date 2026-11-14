"""Per-seat statistics and a leak report from the hand histories kit/fetch_hands.py saves.

    python3 tools/analyze.py hands/                     # stats per round and seat, leaks for our seat
    python3 tools/analyze.py hands/ --emit opponents/   # also write a clone bot per opponent seat
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
from clone_base import DEFAULT, hand_name  # noqa: E402

SHOVE = 800      # a preflop raise to at least this many chips counts as a shove
PRIOR = 10       # a clone's rate starts from this many decisions of the average player
# Rate -> the count it is a share of. Those that are also keys of clone_base.DEFAULT make up a clone's profile.
RATES = {"vpip": "hands", "pfr": "hands", "shove": "hands", "open": "unraised", "limp": "unraised",
         "reraise": "faced_raise", "call_raise": "faced_raise",
         "bet": "checked_to", "raise": "faced_bet", "fold_to_bet": "faced_bet"}
LAST = {"fold": "folded", "call": "called", "raise": "raised", "check": "checked"}
CLONE = '''"""Clone of seat %d in round %s, fitted by tools/analyze.py from %d hands."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from clone_base import make_agent  # noqa: E402

Agent = make_agent(%r)
'''


def load_hands(path):
    """Read one round file. Every guess about the site's field names lives here.

    Returns {"ref", "seat" (ours, or None when it can't be told), "hands"}; each hand is
    {"n", "button", "bb", "events", "results": [chips won per seat], "hole": {seat: [two cards]}}.
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
            if isinstance(results, dict):
                results = [results[s] for s in sorted(results, key=int)]
            if sum(results):
                raise ValueError("hand %d: results sum to %d, expected chips won per seat summing to 0"
                                 % (k, sum(results)))
            hands.append({"n": h.get("n", k + 1), "button": h["button"], "bb": h.get("bb", 20),
                          "events": h["events"], "results": results,
                          "hole": {int(s): c for s, c in (h.get("hole") or {}).items() if c}})
        if not hands:
            raise ValueError("no hands")
        seat = data.get("seat", rd.get("seat"))
        if seat is None:  # ours is the one seat whose cards are there every hand
            always = set.intersection(*(set(h["hole"]) for h in hands))
            if len(always) > 1:  # a seat that never folds shows every hand too; only ours shows cards it folded
                always &= {s for h in hands for s in h["hole"]
                           if any(ev[:3] == ["act", s, "fold"] for ev in h["events"])}
            seat = always.pop() if len(always) == 1 else None
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        first = (data.get("hands") or [None])[0] if isinstance(data, dict) else None
        raise SystemExit("%s: not the shape load_hands expects (%s: %s)\n  top-level keys: %s\n  first hand: %s"
                         % (path, type(e).__name__, e, sorted(data) if isinstance(data, dict) else type(data),
                            sorted(first) if isinstance(first, dict) else first))
    ref = str(rd.get("ref") or os.path.splitext(os.path.basename(path))[0])
    return {"ref": ref, "seat": seat, "hands": hands}


def position(seat, button, n):
    off = (seat - button) % n
    return {n - 1: "CO", 0: "BTN", 1: "SB", 2: "BB"}.get(off, "EP" if off < (n + 2) // 2 else "MP")


def analyse(rnd):
    """Walk one round. Returns (seats, rows): per seat its counts ("c"), first-raise sizes in big blinds
    ("open_bb"), postflop bet sizes as a share of the pot ("bet_pot") and the hands it showed after shoving
    ("shown"); rows has one summary of each hand from our seat, empty when our seat is unknown."""
    n = len(rnd["hands"][0]["results"])
    me = rnd["seat"]
    seats = [{"c": Counter(), "open_bb": [], "bet_pot": [], "shown": Counter()} for _ in range(n)]
    rows = []
    for h in rnd["hands"]:
        bets, pot, street, acted_on, raises = [0] * n, 0, "preflop", "preflop", 0
        entered, raised, shoved, folded, last, line = set(), set(), set(), {}, {}, []
        for ev in h["events"]:
            kind, seat = ev[0], ev[1]
            if kind == "post":
                bets[seat] += ev[2]
                pot += ev[2]
            elif kind == "board":
                street, bets, raises = ev[1], [0] * n, 0
                line.append("| " + " ".join(ev[2][-3 if street == "flop" else -1:]))
            elif kind == "act":
                action, amount = ev[2], ev[3]
                c, top = seats[seat]["c"], max(bets)
                last[seat], acted_on = action, street
                line.append("%s %s%s" % ("us" if seat == me else "s%d" % seat, action, " %d" % amount if amount else ""))
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
            if showdown and i in shoved and i in h["hole"]:
                s["shown"][hand_name(h["hole"][i])] += 1
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


def emit(rnd, seats, out):
    if rnd["seat"] is None:
        raise SystemExit("%s: can't tell which seat is ours, so no clones written" % rnd["ref"])
    os.makedirs(out, exist_ok=True)
    for i, s in enumerate(seats):
        if i == rnd["seat"]:
            continue
        path = os.path.join(out, "clone_%s_%d.py" % (re.sub(r"\W", "_", rnd["ref"]), i))
        with open(path, "w") as f:
            f.write(CLONE % (i, rnd["ref"], s["c"]["hands"], profile(s)))
        print("wrote", path)


def share(c, k, of):
    return "%.0f%%" % (100.0 * c[k] / c[of]) if c[of] else "-"


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
    ap.add_argument("path", help="a folder of round files, or one file")
    ap.add_argument("--emit", metavar="DIR", help="write clone_<round>_<seat>.py per opponent seat (use opponents/)")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.path, "*.json"))) if os.path.isdir(a.path) else [a.path]
    if not files:
        raise SystemExit("no .json files in %s" % a.path)
    rows = []
    for path in files:
        rnd = load_hands(path)
        seats, round_rows = analyse(rnd)
        print_round(rnd, seats)
        rows += round_rows
        if a.emit:
            emit(rnd, seats, a.emit)
    print_leaks(rows, len(files))


if __name__ == "__main__":
    main()
