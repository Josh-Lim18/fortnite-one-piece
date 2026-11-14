"""Turn our bot's decisions into fine-tuning examples for Adaption.

python3 adaption/make_dataset.py --examples 12000 --out adaption/data/poker.jsonl --seed 1 --eval-share 0.1

Plays eight-seat tables in-process; our bot (with unlimited thinking time) takes one seat and
every decision it makes becomes one {"prompt", "completion"} line.
"""
import argparse
import collections
import gc
import glob
import importlib.util
import json
import multiprocessing
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, "kit"), os.path.join(ROOT, "opponents")]

import bot  # noqa: E402
from engine import FixedHandsTable  # noqa: E402
from engine.players import LocalPlayer  # noqa: E402

SEATS = 8
HANDS = 1000
BOT_PARAMS = {"trials": 2000, "decision_ms": 2000, "round_budget_s": 1e9}
PREFLOP_FOLD_KEEP = 0.2
QUESTION = ("What is your action? Answer with exactly one of: fold, check, call, all_in, "
            "or raise <amount>, where <amount> is the total you raise to this street.")


def opponent_files():
    files = sorted(glob.glob(os.path.join(ROOT, "kit", "examples", "*.py")))
    files.append(os.path.join(ROOT, "kit", "bot.py"))
    for path in sorted(glob.glob(os.path.join(ROOT, "opponents", "*.py"))):
        with open(path) as f:
            if "class Agent" in f.read():
                files.append(path)
    return files


_loaded = {}


def load_agent(path):
    if path not in _loaded:
        name = "opp_" + os.path.relpath(path, ROOT).replace(os.sep, "_")[:-3]
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[path] = module.Agent
    return _loaded[path]


def position(seat, button, n):
    off = (seat - button) % n
    if off < 3:
        return ("button", "small blind", "big blind")[off]
    late = {n - 1: "cutoff", n - 2: "hijack", n - 3: "lojack"}
    if off in late:
        return late[off]
    return "under the gun" if off == 3 else "under the gun +%d" % (off - 3)


def corrected(state, move):
    """The action the engine actually plays for `move`, in completion format."""
    move = move or {}
    action = str(move.get("action", "")).lower()
    to_call, legal = state["to_call"], state["legal_actions"]
    if action in ("raise", "bet", "all_in", "allin") and "raise" in legal:
        lo, hi = state["min_raise_to"], state["max_raise_to"]
        try:
            target = hi if action in ("all_in", "allin") else int(move.get("amount"))
        except (TypeError, ValueError, OverflowError):
            target = lo
        target = max(lo, min(target, hi))
        return "all_in" if target == hi else "raise %d" % target
    if action in ("call", "raise", "bet", "all_in", "allin") and to_call > 0:
        return "call"
    return "check" if to_call == 0 else "fold"


def describe(state, agent):
    """Plain-English prompt built only from what the bot sees."""
    me, button, n = state["seat"], state["button"], len(state["stacks"])
    stacks, bets, folded = state["stacks"], state["bets"], state["folded"]
    order = [(button + k) % n for k in range(1, n + 1)]  # small blind first, button last
    name = lambda i: "you (%s)" % position(i, button, n) if i == me else position(i, button, n)
    start = agent.stack
    cap = " Raises are capped at %d per street." % state["raise_cap"] if state["raise_cap"] else ""
    lines = [
        "Game: %s Texas hold'em, %d seats, blinds %d/%d, every hand starts each player on %d chips "
        "(%d big blinds).%s Cards are rank then suit (T = ten; c d h s = clubs diamonds hearts spades)."
        % (state["betting"].replace("_", "-"), n, state["small_blind"], state["big_blind"],
           start, start // state["big_blind"], cap),
        "Your cards: %s." % " ".join(state["hole_cards"]),
        "Street: %s. Board: %s." % (state["street"], " ".join(state["board"]) or "none yet"),
        "Your position: %s. You have %d chips behind and %d in front of you this street."
        % (position(me, button, n), stacks[me], bets[me]),
        "Players still in: %s." % "; ".join(
            "%s, %d behind, %d bet this street" % (name(i), stacks[i], bets[i])
            for i in order if not folded[i]),
        "Pot: %d. To call: %d." % (state["pot"], state["to_call"]),
    ]
    legal = []
    if state["to_call"] > 0:
        legal += ["fold", "call %d" % state["to_call"]]
    else:
        legal.append("check")
    if "raise" in state["legal_actions"]:
        lo, hi = state["min_raise_to"], state["max_raise_to"]
        if lo < hi:
            legal.append("raise <amount> from %d to %d" % (lo, hi - 1))
        legal.append("all_in (raise to %d)" % hi)
    lines.append("Legal actions: %s." % ", ".join(legal))

    by_street, raised = {}, set()
    for h in state["history"]:
        acts = by_street.setdefault(h["street"], [])
        a, amt, who = h["action"], h["amount"], name(h["seat"])
        if a in ("small_blind", "big_blind"):
            acts.append("%s posts %d" % (who, amt))
        elif a == "raise":
            first_bet = h["street"] != "preflop" and h["street"] not in raised
            raised.add(h["street"])
            acts.append("%s %s %d" % (who, "bets" if first_bet else "raises to", amt))
        elif a == "call":
            acts.append("%s calls %d" % (who, amt))
        else:
            acts.append("%s %ss" % (who, a))
    lines.append("Action so far: %s" % " ".join(
        "%s: %s." % (street.capitalize(), ", ".join(acts)) for street, acts in by_street.items()))

    p = agent.p
    lines.append("Opponent profiles so far this round:")
    for i in order:
        if i == me or folded[i]:
            continue
        s = agent._seat(i)
        lines.append(
            "- %s: %d hands seen; enters %.0f%% of pots, raises preflop %.0f%%, bets or raises "
            "%.0f%% of postflop actions, folds to a bet %.0f%%." % (
                position(i, button, n), s.hands,
                100 * agent._rate(s.vpip, s.hands, p["prior_vpip"]),
                100 * agent._rate(s.pfr, s.hands, p["prior_pfr"]),
                100 * agent._rate(s.bets, s.bets + s.passive, p["prior_aggr"]),
                100 * agent._rate(s.folds, s.folds + s.continues, p["prior_fold"])))
    lines.append(QUESTION)
    return "\n".join(lines)


def play_table(args):
    """Play one table; return rows of (hand key, street, prompt, completion)."""
    table, seed, hands = args
    rng = random.Random("%s-%s" % (seed, table))
    pool = opponent_files()
    rows = []

    class Recorder(bot.Agent):
        def __init__(self):
            super().__init__(params=BOT_PARAMS)
            self.rng = random.Random(rng.random())
            gc.enable()  # bot.Agent disables gc for the 10 ms limit; a long-lived worker needs it

        def act(self, state):
            move = super().act(state)
            done = corrected(state, move)
            if state["street"] != "preflop" or done != "fold" or rng.random() < PREFLOP_FOLD_KEEP:
                key = "%s-%d-%d" % (seed, table, state["hand_number"])
                rows.append((key, state["street"], describe(state, self), done))
            return move

    players = [LocalPlayer(load_agent(rng.choice(pool))) for _ in range(SEATS - 1)]
    players.insert(rng.randrange(SEATS), LocalPlayer(Recorder))
    FixedHandsTable(players, hands=hands, seed=rng.random()).play()
    errors = [p.stats.error_samples for p in players if p.stats.errors]
    if errors:
        print("table %d: bot errors %s" % (table, errors[0][0][-300:]), file=sys.stderr)
    return rows


def generate(examples, seed, hands=HANDS, processes=None):
    rows, table = [], 0
    processes = processes or os.cpu_count()
    with multiprocessing.Pool(processes) as pool:
        while len(rows) < examples:
            batch = [(t, seed, hands) for t in range(table, table + processes)]
            table += processes
            for got in pool.map(play_table, batch):
                rows += got
    return rows[:examples]


def split(rows, share, seed):
    """Split by hand, so no hand's decisions land in both files."""
    is_eval = lambda key: random.Random("%s-eval-%s" % (seed, key)).random() < share
    train = [r for r in rows if not is_eval(r[0])]
    return train, [r for r in rows if is_eval(r[0])]


def write(rows, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        for _, _, prompt, completion in rows:
            f.write(json.dumps({"prompt": prompt, "completion": completion}) + "\n")


def eval_path(path):
    base, ext = os.path.splitext(path)
    return base + ".eval" + ext


def summary(rows):
    streets = collections.Counter(r[1] for r in rows)
    actions = collections.Counter(r[3].split()[0] for r in rows)
    return ("by street: %s\nby action: %s" % (
        ", ".join("%s %d" % (s, streets[s]) for s in ("preflop", "flop", "turn", "river")),
        ", ".join("%s %d" % kv for kv in actions.most_common())))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--examples", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--eval-share", type=float, default=0.0)
    a = ap.parse_args()
    t0 = time.time()
    rows = generate(a.examples, a.seed)
    train, ev = split(rows, a.eval_share, a.seed)
    write(train, a.out)
    print("%d examples to %s\n%s" % (len(train), a.out, summary(train)))
    if a.eval_share > 0:
        write(ev, eval_path(a.out))
        print("%d examples to %s\n%s" % (len(ev), eval_path(a.out), summary(ev)))
    print("took %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
