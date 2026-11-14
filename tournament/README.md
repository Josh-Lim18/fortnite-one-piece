# Strategy tournament (lane C)

Scouts find problems, parallel solvers each fix one problem in a different style, an arena picks winners,
runners-up are kept as backups with trigger conditions (`candidates/improved/backups/manifest.yaml`).

- `scouts/*.md` — six scout reports (41 problems: archetypes, adaptive bots, our leaks, multiway, sizing, robustness)
- `SOLVER_BRIEF.md`, `CONTEXT.md` — what solvers were told
- `RESULTS.md` — results. The dependency-free arena used during the tournament is **not** included (review of #12: one arena only).
  Use `arena/` (PokerKit) or `tools/sim.py` on `poker/live` to reproduce.

The bot built from this is `candidates/improved/autopicker_lc` (research only; v1-fast is the live bot).
Solvers stopped early: 4 of 15 finished (preflop/minimal, multiway/minimal, shove-defense/minimal and /balanced).
