"""One intake smoke table using the unmodified supplied kit; not a ranking arena.

python research/checks/smoke_candidates.py --kit PATH --players 8 --seed 1401 \
    --out research/runs/smoke-8.json candidates/imported/example.py
Run sequentially, without competing CPU-heavy jobs. Never relax the limits.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys
import time


ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packaging(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), feature_version=(3, 12))
    imports = sorted({name for node in ast.walk(tree)
                      for name in ([a.name.split(".")[0] for a in node.names]
                                   if isinstance(node, ast.Import) else
                                   [node.module.split(".")[0]]
                                   if isinstance(node, ast.ImportFrom) and node.module else [])})
    assert path.stat().st_size <= 200000, "submission exceeds conservative 200KB cap"
    assert all(name in sys.stdlib_module_names for name in imports), imports
    assert any(isinstance(n, ast.ClassDef) and n.name == "Agent" for n in tree.body)
    return dict(bytes=path.stat().st_size, sha256=sha(path), imports=imports,
                python_312_grammar=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bots", nargs="+")
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--players", type=int, choices=(7, 8), default=8)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--hands", type=int, default=1000)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("output already exists; use a new run ID")
    if not 1 <= len(args.bots) <= args.players or args.hands < 1:
        parser.error("invalid bot or hand count")
    kit = args.kit.resolve()
    sys.path.insert(0, str(kit))
    from engine import FixedHandsTable
    from engine.players import SubprocessPlayer

    class AuditedPlayer(SubprocessPlayer):
        def __init__(self, path):
            super().__init__(str(path), timeout_ms=10, bank_ms=10000)
            self.invalid = []
            self.invalid_count = 0

        def act(self, state):
            response = super().act(state)
            if not response or response.get("type") != "action":
                return response
            action = response.get("action")
            valid = action in state["legal_actions"] or action == "all_in"
            if action == "raise":
                amount = response.get("amount")
                valid = ("raise" in state["legal_actions"] and type(amount) is int
                         and state["min_raise_to"] <= amount <= state["max_raise_to"])
            if not valid:
                self.invalid_count += 1
                if len(self.invalid) < 3:
                    self.invalid.append(dict(response=response, state=state))
            return response

    candidates = [Path(p).resolve() for p in args.bots]
    packages = {p.relative_to(ROOT).as_posix(): packaging(p) for p in candidates}
    roster = list(candidates)
    house = [kit / "examples" / f for f in
             ("tight_aggressive.py", "calling_station.py", "random_bot.py")]
    while len(roster) < args.players:
        roster.append(house[(len(roster) - len(candidates)) % len(house)])
    players = [AuditedPlayer(p) for p in roster]
    start = time.perf_counter()
    try:
        result = FixedHandsTable(players, hands=args.hands,
                                 config={"betting": "no_limit", "starting_stack": 2000,
                                         "fixed_blinds": (10, 20), "raise_cap": None},
                                 seed=args.seed).play()
        live_flags = [dict(dead=p.dead, stalled=p.stalled, flooded=p.flooded,
                           process_exit_before_close=p.proc.poll() if p.proc else "not_started")
                      for p in players]
    finally:
        for p in players:
            p.close()
    assert sum(result["chips"]) == 0, "chip conservation failed"
    rows = []
    for seat, (path, player) in enumerate(zip(roster, players)):
        is_candidate = path in candidates
        rows.append(dict(seat=seat,
                         bot=(path.relative_to(ROOT) if is_candidate else path.relative_to(kit)).as_posix(),
                         candidate=is_candidate, sha256=sha(path),
                         chips=result["chips"][seat], hands=result["hands"],
                         bb_per_100=result["chips"][seat] / 20 / result["hands"] * 100,
                         **player.stats.as_dict(), total_think_ms=round(player.stats.total_ms, 3),
                         load_error=player.load_error, **live_flags[seat],
                         invalid_actions=player.invalid_count, invalid_examples=player.invalid))
    reliable = all(not any((r["timeouts"], r["errors"], r["bank_out"],
                           r["load_error"], r["invalid_actions"], r["dead"], r["stalled"], r["flooded"]))
                   and r["process_exit_before_close"] is None
                   for r in rows if r["candidate"])
    report = dict(kind="candidate_intake_smoke_not_ranking",
                  created_utc=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), platform=platform.platform(),
                  target_python="3.12",
                  target_python_runtime_verified=sys.version_info[:2] == (3, 12),
                  seed=args.seed, player_count=args.players, hands=args.hands,
                  timeout_ms=10, bank_ms=10000, starting_stack=2000, blinds=[10, 20],
                  betting="no_limit", elapsed_seconds=round(time.perf_counter() - start, 3),
                  engine_hashes={p.relative_to(kit).as_posix(): sha(p)
                                 for p in sorted((kit / "engine").glob("*.py"))},
                  packaging=packages, rows=rows, candidate_reliability_pass=reliable,
                  limitations=["One fixed roster/seat assignment/seed is not competitive evidence.",
                               "Monte Carlo wall-clock cutoffs and house RNG may change outcomes.",
                               "Local subprocesses do not reproduce the sealed platform sandbox."])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(report, output, indent=2)
        output.write("\n")
    print(json.dumps({"report": str(args.out), "candidate_reliability_pass": reliable,
                      "candidates": [{k: r[k] for k in ("bot", "bb_per_100", "timeouts", "errors",
                                     "bank_out", "invalid_actions", "total_think_ms")}
                                     for r in rows if r["candidate"]]}, indent=2))
    return 0 if reliable else 1


if __name__ == "__main__":
    raise SystemExit(main())
