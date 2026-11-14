# Slice: a gate pool that plays like the real field

Owner: Opus subagent, overnight. Time box: 3 hours. Commit progress at least once an hour, so a pause loses nothing. Decided by Owen, Sat 14 Nov 19:00 GMT. Sunday uploads open at 09:00.

## Why
`notes/field-report.md`, last section "Why Joca loses". On the platform, v1-fast lost −22.4 bb/100 over 22 rounds (r024–r045), yet it beats our 38 clones in `opponents/real/` by about +123. So every gate we ran tonight measured against opponents far softer than the real field. Compared with the teams that win at our tables, Joca plays tight preflop, passive postflop (raises ÷ calls 1.18 against about 2.9) and sticky when bet into (it folds to a postflop bet 33% of the time against about 50%). It wins little without showdown and loses at showdown. The clones don't reproduce the field's value-heavy betting.

## Data (read-only)
`~/Downloads/poker-v1/hands/saturday_r*.json` and `saturday_practice_r*.json`: every hand of every round we played. The format is described in `notes/slice-real-data.md` ("The data"). `players` names every seat's team; hole cards appear only at showdown; `round.version` is our upload: 4 is v1-fast (r024–r045), 5 is PR #14's bot (r046 on). A starting script that computes per-team VPIP, PFR, aggression and fold-to-bet is at `/private/tmp/claude-502/-Users-owenyan-Library-Application-Support-Claude-scratch-workspaces-d75be534-e048-422d-851e-e508111d2197-9cdf90a5-c3b1-4330-bafd-ae0a0b43eea2-scratch-2026-11-14-5fa2e3/0c20d5e8-5814-4e2b-ae17-154774efb0d6/scratchpad/why_losing.py`.

## Build
1. **`tools/field_stats.py`:** per-team stats from the hand files, enough to calibrate a bot to: VPIP, PFR and 3-bet by position; c-bet; postflop bet/raise frequency and fold-to-bet by street; bet sizes as a share of the pot by street; showdown frequency; and how strong hands are when they bet big (from showdowns). Add a test (`tools/test_field_stats.py`) on a small hand-made round.
2. **Calibrated pool `opponents/field/`:** one bot per team with enough hands, tuned so that its stats in our simulator match the team's real stats. Either tune the existing clones (`opponents/real/`, `opponents/clone_base.py`) or write one parametric clone; your call, say which. State the tolerance you hit per stat (aim for about ±3 points on VPIP, PFR and fold-to-bet, and ±20% on aggression), and list the teams you couldn't reach.
3. **Validation (the acceptance test):** replay each real round's table with the calibrated bots of those exact teams in the file's seat order, v1-fast in our seat, several seeds each. Compare predicted with actual bb/100: v1-fast's 22 rounds averaged −22.4 (aim to land within about 10). Also compare predicted with actual results for the teams at our tables, to see whether the pool ranks them right. If the pool can't get near the real numbers, say so plainly and say what's missing. A pool that doesn't predict the field is not a gate.
4. **Re-gate on the new pool** (`tools/sim.py`, same deals, 128 rounds, seed 2), each against v1-fast (`notes/bot-v1-fast.py`):
   - the live bot, PR #14: `git show origin/layer1-2/equity-fix-layer2:bot.py`;
   - PR #15: `git show origin/layer1/range-equity-lookup:bot.py` (same decisions, about half the time);
   - B, the equity network + governor: `git show equity/live:bot.py`.
5. **If time remains:** parameter sensitivity of the live bot on the new pool. Sweep one `PARAMS` group at a time through overrides in a tool, never by editing `bot.py`:
   - (a) calling a postflop bet or raise;
   - (b) postflop betting and raising frequency;
   - (c) preflop opening width.
   Same deals, then report which direction gains and by how much. This is evidence for Anh (layer 1 is Anh's), not a change to ship.

## Rules
- Files you own: `tools/field_stats.py`, `tools/test_field_stats.py`, `opponents/field/`, any sweep tool under `tools/`, and `notes/reports/field-pool.md`. Never edit `bot.py`, `kit/` or `opponents/real/`.
- Opponent bots: Python standard library only.
- Team names stay local: commit only on your worktree branch. Never push, never post on the team board. Local `main` is never pushed.
- `scripts/verify.sh` must print READY at the end.
- The laptop may be shared; run long jobs in the background and use the cores sensibly.

## Done
Report in `notes/reports/field-pool.md`, committed, and as your final message:
- the calibration table (real vs simulated stats per team);
- the validation (predicted vs actual);
- the re-gate numbers;
- any sweep results;
- what is not done or not verified.
