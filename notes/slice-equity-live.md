# Slice: equity network and time governor in the live line

Owner: Opus subagent. Time box: 60 minutes. Decided by Owen, Sat 14 Nov 18:10 GMT. Target: Sunday's 09:00 upload window, after a rebase onto Anh's v1-fast fixes (not yours to do).

## Base
Branch `layer2/live` at `3d03277`: v1-fast (the live bot) plus layer 2, verify READY, 1.01x v1-fast's thinking. In your worktree run `git switch -c equity/live 3d03277` and build there. Local `main` is a different line (its `bot.py` is another bot); take only the pieces named below from it.

## What to build (read SPEC.md "Time budget" first)
1. **Equity network.** `main` already has it: `equity_net/` (tag `equity-net-1`) and, in `main:bot.py`, the pasted section starting `# ---- equity network, pasted from ...`, `PARAMS["equity_net"]`, and the net branch at the top of `Agent._equity`. Bring `equity_net/` over with `git checkout main -- equity_net/` and port the pasted section, the param and the `_equity` branch into this line's `bot.py`, adapted to v1-fast's `_equity` (40 trials, `round_budget_s`, `round_stop_s`). Measured on main: mean error 0.026 vs the Monte Carlo's 0.080, 0.57x the time. v1-fast's Monte Carlo also has a known bias (`if t & 3: continue` keeps one in four out-of-range deals); the net replaces that path when on, and keep the Monte Carlo path as it is for when the param is off (Anh owns that code and is fixing it).
2. **Time governor** (SPEC.md "Time budget"). The bot compares its own thinking so far (`self.spent`) with its pace for the hands played, against the 5 s a 1,000-hand round target. Map the SPEC's steps onto what this bot has (it has no picker): past 1.2x pace and past 1.5x pace each step down to a cheaper equity estimate, and past `round_stop_s` the cheapest one. Measure what each step costs and say which estimate each step uses. Every threshold and step is a param. On the laptop it should almost never fire; prove each step fires by forcing the params in a test.

## Files you own
`bot.py`, `equity_net/` (copied from main), `tools/test_bot.py`. Do not change `tools/baseline_bot.py` (it is v1-fast, the comparison baseline) or anything in `kit/`. Python standard library only in `bot.py`; it must run on Python 3.12 and stay under 200 KB.

## Gate (report every number)
- `scripts/verify.sh` prints READY.
- Lane D's check from the repo root: `python3 team/tests/check_submission.py bot.py --kit kit --reference notes/bot-v1-fast.py` (`team/` and `notes/bot-v1-fast.py` are in the main checkout, not your worktree; use their absolute paths). The own-thinking estimate must be at most 5 s and should be at most layer 2's 2.04 s. Note: its subprocess timeout lines are wall time and read high when the laptop is busy; report them with the load average.
- Same deals vs `layer2/live` (3d03277) with `tools/sim.py`: `opponents/real` 128 rounds, plus kit/examples and kit/bot.py 32 rounds each. No pool may lose beyond its error bars.
- The governor tests pass.

## Done
Commit on `equity/live` as `Owen Yan <100368790+owenbonc@users.noreply.github.com>`, no co-author lines. Don't push, don't post on the team board, don't merge into any other branch. Write your report to `notes/reports/equity-live.md` in your worktree, commit it, and return it as your final message: commits, the gate numbers, the governor's steps and their costs, anything not done or not verified. Anything you'd do differently than this brief says: say so in the report, don't improvise.
