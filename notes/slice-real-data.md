# Slice: learn from the real field

**Files you own:** `tools/analyze.py`, `model/` (dataset, fit, evaluate, profiler, fitted), `opponents/real/` (new), `tools/test_analyze.py`, `notes/field-report.md` (new). **Time box:** 75 minutes; report by 18:15 at the latest. Uploads close at 19:30 and the best bot must be chosen before then. Do not edit `bot.py`.

## The data

`<ROOT>/hands/*.json` (gitignored; `<ROOT>` is the folder holding `notes/`): 16 practice rounds and 21+ counted rounds, one file per round, each 1,000 hands at one 5–8 seat table. The real format (it differs from what `load_hands` guessed):
- top level:
  - `ref`
  - `seat`: our seat
  - `players`: team names by seat. This is the key fact: every seat is identified by team, across rounds.
  - `format`
  - `hands`
  - `round`: `version` (our bot's upload number), `bb100`, `think_s`, `timeouts`, `errors`, `bank_out` and more
- each hand:
  - `n`, `button`, `sb`, `bb`, `start_stacks`
  - `hole`: our cards only
  - `showdown`: cards of seats that reached showdown
  - `board`
  - `events`: the same list as `kit/fetch_hands.py` documents
  - `results`: chips per seat
  - `result`

Joca is our team. Our versions: practice v1 (not ours), counted v2 (not ours, 15:00–16:35), v3 = our demo-1 (from 16:40), v4 = v1-fast (`notes/bot-v1-fast.py`, from about 16:55).

## Build

1. **Loaders.** Fix `load_hands` in `tools/analyze.py` and the real-file path in `model/dataset.py` for this format, keyed by team name as well as seat.
2. **`notes/field-report.md`:**
   - **Per team:** hands observed; how often it enters a pot, raises preflop, re-raises, shoves; postflop aggression; fold-to-bet by size bucket; bet sizes and whether they follow a fixed formula (the starter's is `min_raise_to + pot // 2`); showdown hands by line; its chips against the table.
   - **Groupings:** which teams look like the starter, a calling station, a maniac or a nit, and which are the strong ones.
   - **What separates winners from losers** in this field, in a few lines a person can act on.
3. **Layer 2 refit** on the real hands (counted plus practice) together with the simulated rounds. Search k from 4 to 12, scored by held-out log-loss on real rounds held out by round. Report:
   - real held-out log-loss for prior only, counts, and the full model;
   - the calibration table on real rounds;
   - `fitted.py`'s size.
4. **Clones** of each real team with at least about 2,000 observed decisions, written to `opponents/real/clone_<team>.py` from their measured rates (use or extend `opponents/clone_base.py`). Check that each clone's own stats come out close to the team's.
5. **Pick the bot to upload:**
   - Compare with `tools/sim.py --vs` against a pool of the real clones (seated by how often each team appeared): `notes/bot-v1-fast.py` (the incumbent), the `demo-2` bot (`git show demo-2:bot.py`), and the `picker-1` bot (`git show picker-1:bot.py`, with its profiler refit if that is quick).
   - Use at least 24 rounds each, mean ± standard error.
   - Also report each bot's own thinking time per round in-process, as a ratio to v1-fast's. The tournament machine is 10–15x slower than this laptop: v1 used 9.1 s of the 10 s bank there. Anything over 1.0x v1-fast's own time is not uploadable as is.

## Done

Besides the common brief:
- the field report's top findings;
- the refit numbers;
- the comparison table;
- a one-line recommendation: which file to upload before 19:30, or keep v1-fast.
