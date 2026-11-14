"""Command line: list the bots, seat some at a table, run a heads-up round robin, or replay a run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

from arena.engine import TableConfig
from arena.match import run_match, run_round_robin, run_table_until_decided, run_until_decided
from arena.registry import load_registry
from arena.stats import BotStats, format_leaderboard, summarize
from arena.viewer import build_viewer


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "list":
        for name in load_registry(args.bots):
            print(name)
        return 0
    if args.command == "view":
        run_dir = Path(args.run) if args.run else _latest_run(Path(args.out))
        if run_dir is None:
            print(f"no runs in {args.out}/", file=sys.stderr)
            return 2
        page = build_viewer(run_dir, max_hands=args.max_hands)
        print(f"Replay written to {page}")
        if not args.no_open:
            webbrowser.open(page.resolve().as_uri())
        return 0

    out = Path(args.out) / f"{datetime.now():%Y%m%d-%H%M%S}-{args.command}"
    out.mkdir(parents=True, exist_ok=True)
    factories = load_registry(args.bots, log_dir=out)
    names = args.names or list(factories)
    unknown = [n for n in names if n not in factories]
    if unknown:
        print(f"unknown bots: {', '.join(unknown)}. Known: {', '.join(factories)}", file=sys.stderr)
        return 2
    if len(set(names)) != len(names):
        print("each bot can take only one seat", file=sys.stderr)
        return 2
    if args.command == "table" and not 2 <= len(names) <= 9:
        print("a table seats 2-9 bots", file=sys.stderr)
        return 2
    if args.command == "roundrobin" and len(names) < 2:
        print("a round robin needs at least 2 bots", file=sys.stderr)
        return 2
    config = TableConfig(args.sb, args.bb, args.stack)
    run_info = {
        "command": args.command,
        "bots": names,
        "deals": args.deals,
        "seed": args.seed,
        "config": {"small_blind": args.sb, "big_blind": args.bb, "starting_stack": args.stack},
    }
    (out / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")

    with open(out / "hands.jsonl", "w", encoding="utf-8") as log:

        def on_hand(record):
            log.write(json.dumps(record.to_dict()) + "\n")

        def on_batch(deals, standings):
            log.flush()
            top = standings.leaderboard[:2]
            gap = " vs ".join(f"{r.name} {r.mbb_per_hand:.0f} +/- {r.ci95:.0f}" for r in top)
            status = "DECIDED" if standings.decided else "not yet separated"
            unit = "deals per pair" if args.command == "roundrobin" else "deals"
            print(f"after {deals} {unit}: {gap} ({status})", flush=True)

        if args.command == "table":
            bots = [factories[n]() for n in names]
            try:
                if args.until_decided:
                    result = run_table_until_decided(bots, args.deals, args.max_deals, args.seed, config,
                                                     on_hand, on_batch)
                    leaderboard = result.leaderboard
                else:
                    hands = run_match(bots, args.deals, args.seed, config, on_hand)
                    leaderboard = summarize(hands, config.big_blind)
            finally:
                for bot in bots:
                    bot.close()
        elif args.until_decided:

            result = run_until_decided({n: factories[n] for n in names}, args.deals, args.max_deals, args.seed,
                                       config, on_hand, on_batch)
            leaderboard = result.leaderboard
            _write_pairwise(out / "pairwise.csv", names, result.pairwise)
        else:
            result = run_round_robin({n: factories[n] for n in names}, args.deals, args.seed, config, on_hand)
            leaderboard = result.leaderboard
            _write_pairwise(out / "pairwise.csv", names, result.pairwise)

    _write_leaderboard(out / "leaderboard.csv", leaderboard)
    print(format_leaderboard(leaderboard))
    if args.until_decided:
        unit = "deals per pair" if args.command == "roundrobin" else "deals"
        verdict = f"Winner: {leaderboard[0].name}" if result.decided else f"No clear winner after {result.deals} {unit}"
        run_info.update(deals=result.deals, decided=result.decided, winner=leaderboard[0].name)
        (out / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
        print(f"\n{verdict}")
    print(f"\nResults in {out}")
    if args.view:
        page = build_viewer(out)
        webbrowser.open(page.resolve().as_uri())
        print(f"Replay: {page}")
    return 0


def _latest_run(out: Path) -> Path | None:
    runs = sorted(p for p in out.glob("*") if (p / "hands.jsonl").exists()) if out.exists() else []
    return runs[-1] if runs else None


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--bots", default="bots.toml", help="bot registry (default: bots.toml)")

    parser = argparse.ArgumentParser(prog="arena", description="Bot-vs-bot no-limit hold'em arena (duplicate matches).")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", parents=[common], help="list the registered bots")
    for command, nargs, help_text in (
        ("table", "+", "seat 2-9 bots at one table and rotate seats every deal"),
        ("roundrobin", "*", "heads-up duplicate match between every pair (default: every bot)"),
    ):
        p = sub.add_parser(command, parents=[common], help=help_text)
        p.add_argument("names", nargs=nargs, help="bot names from the registry")
        p.add_argument("--deals", type=int, default=500, help="deals per match; each is played once per seat (default 500)")
        p.add_argument("--seed", type=int, default=1, help="card seed; same seed means same cards (default 1)")
        p.add_argument("--sb", type=int, default=5, help="small blind (default 5)")
        p.add_argument("--bb", type=int, default=10, help="big blind (default 10)")
        p.add_argument("--stack", type=int, default=1000, help="chips each bot starts every hand with (default 1000)")
        p.add_argument("--out", default="results", help="folder for result files (default results/)")
        p.add_argument("--view", action="store_true", help="open the replay viewer when the run finishes")
        p.add_argument("--until-decided", action="store_true",
                       help="repeat batches of --deals new deals until the leader's 95%% interval clears second place")
        p.add_argument("--max-deals", type=int, default=5000,
                       help="with --until-decided: stop after this many deals (per pair in a round robin; default 5000)")
    v = sub.add_parser("view", help="open a replay of a run in the browser (default: the latest run)")
    v.add_argument("run", nargs="?", help="results folder (default: newest folder in --out)")
    v.add_argument("--out", default="results", help="where runs live (default results/)")
    v.add_argument("--max-hands", type=int, default=3000, help="hands to embed in the page (default 3000)")
    v.add_argument("--no-open", action="store_true", help="write viewer.html without opening a browser")
    return parser


def _write_leaderboard(path: Path, rows: list[BotStats]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bot", "hands", "chips", "mbb_per_hand", "ci95", "fixed", "errors", "avg_ms", "max_ms"])
        for r in rows:
            writer.writerow(
                [r.name, r.hands, r.chips, f"{r.mbb_per_hand:.2f}", f"{r.ci95:.2f}", r.fixed, r.errors,
                 f"{r.avg_ms:.3f}", f"{r.max_ms:.2f}"]
            )


def _write_pairwise(path: Path, names: list[str], pairwise: dict[tuple[str, str], BotStats]) -> None:
    """Matrix of mbb/hand: row bot's result against column bot."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["bot vs opponent", *names])
        for a in names:
            writer.writerow([a, *("" if a == b else f"{pairwise[(a, b)].mbb_per_hand:.1f}" for b in names)])


if __name__ == "__main__":
    sys.exit(main())
