"""The gate before any upload: the constraints the tournament enforces, one line per check.

    python3 tests/check_submission.py BOT.py --reference V1_FAST.py [--kit PATH] [--hands 1000]

Re-runs itself under Python 3.12 (`uv run --python 3.12`), the tournament's version, and exits
non-zero when any check fails.
"""
import argparse
import ast
import importlib
import importlib.util
import os
import random
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BYTES = 200_000
TIMEOUT_MS, BANK_S = 10.0, 10.0
MAX_TIMEOUT_SHARE, MAX_THINK_S = 0.01, 5.0
# v1-fast's own thinking in real round r024; scaled by the in-process ratio, since load skews laptop seconds.
REFERENCE_PLATFORM_S = 2.03
# The team's target: half the 10 s bank.
PLATFORM_LIMIT_S = 5.0
# Below a millisecond the reference's total is timer noise, not thinking.
MIN_REFERENCE_S = 0.001
OWN_SEATS, OWN_SEED = 7, 1
# (betting, raise_cap): every format the organisers can switch on; fixed_limit caps at 4 by default.
FORMATS = [("no_limit", 0), ("pot_limit", 0), ("fixed_limit", 0), ("no_limit", 3)]
HOUSE = ["tight_aggressive.py", "calling_station.py", "random_bot.py"]
SEATS = 8


def under_312():
    """Replace this process with the same command under Python 3.12, unless already there."""
    if sys.version_info[:2] == (3, 12):
        return
    cmd = ["uv", "run", "--no-project", "--python", "3.12", "python", os.path.abspath(__file__)] + sys.argv[1:]
    try:
        sys.exit(subprocess.call(cmd))
    except FileNotFoundError:
        sys.exit("uv is not installed, so the checks can't run under Python 3.12 as the tournament does.")


def static_checks(path):
    """Size, syntax, stdlib-only imports and a top-level Agent class. Returns [(ok, line)]."""
    data = open(path, "rb").read()
    out = [(len(data) <= MAX_BYTES, "size: %d bytes (limit %d)" % (len(data), MAX_BYTES))]
    try:
        tree = ast.parse(data, path, feature_version=(3, 12))
    except SyntaxError as e:
        return out + [(False, "syntax: not valid Python 3.12: %s" % e)]
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.split(".")[0] not in sys.stdlib_module_names]
        elif isinstance(node, ast.ImportFrom):
            if node.level or node.module.split(".")[0] not in sys.stdlib_module_names:
                bad.append("." * node.level + (node.module or ""))
    out.append((not bad, "imports: standard library only" if not bad else "imports: not standard library: %s"
                % ", ".join(sorted(set(bad)))))
    has_agent = any(isinstance(n, ast.ClassDef) and n.name == "Agent" for n in tree.body)
    out.append((has_agent, "Agent: top-level class found" if has_agent else "Agent: no top-level class Agent"))
    return out


def load(path, name):
    """Import a bot file in this process under its own module name and return its Agent class."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Agent


def seeded(cls, seed):
    def make():
        agent = cls()
        if hasattr(agent, "rng"):
            agent.rng = random.Random(seed)
        return agent
    return make


def own_round(classes, hands):
    """One seeded no-limit round in-process; returns seat 0's act CPU seconds, on_hand_end CPU seconds and decisions."""
    from engine import FixedHandsTable
    from engine.players import LocalPlayer
    random.seed(OWN_SEED)
    players = [LocalPlayer(seeded(c, OWN_SEED * 1009 + i)) for i, c in enumerate(classes)]
    bot, spent = players[0], {"act": 0.0, "end": 0.0}

    # Thread CPU time, not wall time: other work on the laptop inflated wall time 3x and flipped the verdict.
    def timed(name, fn):
        def run(arg):
            t0 = time.thread_time()
            try:
                return fn(arg)
            finally:
                spent[name] += time.thread_time() - t0
        return run
    bot.act, bot.hand_end = timed("act", bot.act), timed("end", bot.hand_end)
    FixedHandsTable(players, hands=hands, config={"betting": "no_limit"}, seed=OWN_SEED).play()
    if bot.stats.errors:
        raise RuntimeError("act raised %d time(s), first:\n%s" % (bot.stats.errors, bot.stats.error_samples[0]))
    return spent["act"], spent["end"], bot.stats.decisions


def own_check(path, reference, kit, hands):
    """The bot's own thinking against the reference's, transport excluded: the same seeded round against the
    kit's bots, played reference, candidate, reference, candidate so both see the same load; each bot's lower total
    counts."""
    others = [importlib.import_module(h[:-3]).Agent for h in HOUSE] + [load(os.path.join(kit, "bot.py"), "kit_bot")]
    runs = {"reference": [], "candidate": []}
    for role, bot in [("reference", reference), ("candidate", path)] * 2:
        try:
            # A fresh import each run, so module-level caches never warm a bot's second run.
            classes = [load(bot, role)] + [others[i % len(others)] for i in range(OWN_SEATS - 1)]
            runs[role].append(own_round(classes, hands))
        except Exception as e:
            return False, "own thinking: %s %s failed in-process: %s: %s" % (role, bot, type(e).__name__, e)
    best = {role: min(r, key=lambda x: x[0] + x[1]) for role, r in runs.items()}
    ref_total, cand_total = sum(best["reference"][:2]), sum(best["candidate"][:2])
    if ref_total < MIN_REFERENCE_S:
        return False, ("own thinking: reference %s thought only %.6f s in %d hands, too little to divide by; pass "
                       "v1-fast as --reference" % (reference, ref_total, hands))
    ratio = cand_total / ref_total
    estimate = REFERENCE_PLATFORM_S * ratio
    lines = ["own thinking: about %.2f s a 1,000-hand round on the platform = %.2f s (v1-fast, round r024) x ratio "
             "%.2f (limit %.1f s)" % (estimate, REFERENCE_PLATFORM_S, ratio, PLATFORM_LIMIT_S)]
    for role, bot in (("candidate", path), ("reference", reference)):
        act_s, end_s, decisions = best[role]
        lines.append("  %s: %.3f s = act %.3f s + on_hand_end %.3f s, %d decisions, %.3f ms a decision "
                     "(lower of %.3f s and %.3f s): %s" % (role, act_s + end_s, act_s, end_s, decisions,
                                                          1000 * (act_s + end_s) / max(decisions, 1),
                                                          sum(runs[role][0][:2]), sum(runs[role][1][:2]), bot))
    lines.append("  in-process, no_limit, %d hands, %d seats, thread CPU time" % (hands, OWN_SEATS))
    return estimate <= PLATFORM_LIMIT_S, "\n".join(lines)


def play_checks(path, reference, kit, hands):
    """Import and construct Agent(), play one round per format through the kit's subprocess player, then time
    the bot's own thinking in-process."""
    sys.path.insert(0, kit)
    from engine import FixedHandsTable
    from engine.players import LocalPlayer, SubprocessPlayer
    sys.path.insert(0, os.path.join(kit, "examples"))
    house = [importlib.import_module(h[:-3]).Agent for h in HOUSE]

    probe = SubprocessPlayer(path)
    try:
        probe.start_table(0, {"seat": 0, "num_players": SEATS, "format": "fixed_hands", "hands": hands,
                              "starting_stack": 2000, "stacks_reset_each_hand": True, "small_blind": 10,
                              "big_blind": 20, "betting": "no_limit", "raise_cap": None})
        error = probe.load_error
    finally:
        probe.close()
    if error:
        return [(False, "load: import or Agent() failed under Python %s:\n%s" % (sys.version.split()[0], error))]
    out = [(True, "load: imports and constructs Agent() under Python %s" % sys.version.split()[0])]

    for k, (betting, cap) in enumerate(FORMATS):
        me = k % SEATS
        others = [LocalPlayer(house[i % len(house)]) for i in range(SEATS - 1)]
        bot = SubprocessPlayer(path, timeout_ms=TIMEOUT_MS, bank_ms=BANK_S * 1000)
        players = others[:me] + [bot] + others[me:]
        try:
            FixedHandsTable(players, hands=hands, config={"betting": betting, "raise_cap": cap}, seed=k + 1).play()
        finally:
            bot.close()
        st = bot.stats
        share = st.timeouts / max(st.decisions, 1)
        think = st.total_ms / 1000
        ok = not st.errors and share <= MAX_TIMEOUT_SHARE and think <= MAX_THINK_S and not st.bank_out
        name = betting + (", raise cap %d" % cap if cap else "")
        line = ("round (%s, %d hands): %d decisions, %d errors, %d timeouts (%.2f%%), %d bank-outs, "
                "worst decision %.1f ms, thinking %.2f s" % (name, hands, st.decisions, st.errors, st.timeouts,
                                                              100 * share, st.bank_out, st.max_ms, think))
        if st.error_samples:
            line += "\n  first error:\n" + st.error_samples[0]
        out.append((ok, line))
    return out + [own_check(path, reference, kit, hands)]


def main():
    under_312()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot")
    ap.add_argument("--kit", default=os.path.join(REPO, "kit"), help="the organisers' starter kit (default: kit/)")
    ap.add_argument("--hands", type=int, default=1000, help="hands per round (tournament: 1000)")
    ap.add_argument("--reference", required=True,
                    help="the bot whose platform time is known (v1-fast); own thinking is timed against it")
    a = ap.parse_args()
    kit = os.path.abspath(a.kit)
    if not os.path.isfile(os.path.join(kit, "engine", "players.py")):
        sys.exit("No starter kit at %s: pass --kit PATH to the organisers' kit folder (the one holding engine/)."
                 % kit)
    if not os.path.isfile(a.bot) or not a.bot.endswith(".py"):
        sys.exit("%s is not a .py file; the upload is one Python file." % a.bot)
    path = os.path.abspath(a.bot)
    if not os.path.isfile(a.reference) or not a.reference.endswith(".py"):
        sys.exit("--reference %s is not a .py file; pass v1-fast's bot file." % a.reference)
    reference = os.path.abspath(a.reference)

    results = static_checks(path)
    results += play_checks(path, reference, kit, a.hands)
    for ok, line in results:
        print("%s  %s" % ("PASS" if ok else "FAIL", line))
    failed = sum(not ok for ok, _ in results)
    print("Limits: errors 0, timeouts at most %.0f%% of decisions, at most %.0f s thinking a round (bank %.0f s), "
          "at most %.1f s own thinking (act plus on_hand_end) a round on the platform, estimated as %.2f s x "
          "this bot's in-process own thinking / the reference's." % (100 * MAX_TIMEOUT_SHARE, MAX_THINK_S, BANK_S,
                                                                     PLATFORM_LIMIT_S, REFERENCE_PLATFORM_S))
    print("This laptop is not the tournament sandbox (one CPU core, 512 MB, sealed container): "
          "timings here are a guide, not a guarantee.")
    print("%s: %s" % (a.bot, "%d check(s) failed" % failed if failed else "all checks passed"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
