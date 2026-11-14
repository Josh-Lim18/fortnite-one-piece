"""The gate before any upload: the constraints the tournament enforces, one line per check.

    python3 tests/check_submission.py BOT.py [--kit PATH] [--hands 1000]

Re-runs itself under Python 3.12 (`uv run --python 3.12`), the tournament's version, and exits
non-zero when any check fails.
"""
import argparse
import ast
import importlib
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BYTES = 200_000
TIMEOUT_MS, BANK_S = 10.0, 10.0
MAX_TIMEOUT_SHARE, MAX_THINK_S = 0.01, 5.0
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


def play_checks(path, kit, hands):
    """Import and construct Agent(), then play one round per format through the kit's subprocess player."""
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
    return out


def main():
    under_312()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bot")
    ap.add_argument("--kit", default=os.path.join(REPO, "kit"), help="the organisers' starter kit (default: kit/)")
    ap.add_argument("--hands", type=int, default=1000, help="hands per round (tournament: 1000)")
    a = ap.parse_args()
    kit = os.path.abspath(a.kit)
    if not os.path.isfile(os.path.join(kit, "engine", "players.py")):
        sys.exit("No starter kit at %s: pass --kit PATH to the organisers' kit folder (the one holding engine/)."
                 % kit)
    if not os.path.isfile(a.bot) or not a.bot.endswith(".py"):
        sys.exit("%s is not a .py file; the upload is one Python file." % a.bot)
    path = os.path.abspath(a.bot)

    results = static_checks(path)
    results += play_checks(path, kit, a.hands)
    for ok, line in results:
        print("%s  %s" % ("PASS" if ok else "FAIL", line))
    failed = sum(not ok for ok, _ in results)
    print("Limits: errors 0, timeouts at most %.0f%% of decisions, at most %.0f s thinking a round (bank %.0f s)."
          % (100 * MAX_TIMEOUT_SHARE, MAX_THINK_S, BANK_S))
    print("This laptop is not the tournament sandbox (one CPU core, 512 MB, sealed container): "
          "timings here are a guide, not a guarantee.")
    print("%s: %s" % (a.bot, "%d check(s) failed" % failed if failed else "all checks passed"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
