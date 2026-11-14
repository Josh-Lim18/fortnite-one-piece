# Slice: layer 3 autopicker

**Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`, `model/` (only to paste the profiler and its fitted constants in; report any change to them). **Time box:** 90 minutes. Starts only after the layer 2 model slice (`notes/slice-model.md`) is merged.

The design and the skill contract are in the team's Notion operating brief, "Layer 3: the autopicker and the skill contract", copied here so you don't need Notion:

- **Each decision:**
  1. Find the opponents who matter: facing a bet, the bettor; when we bet, the players still to act.
  2. Ask every skill whether it applies.
  3. Price each skill that applies with layer 2's predictions. For a bet: fold chance × pot + call chance × (equity when called × final pot − our bet). Compare it with the base move priced the same way.
  4. Play the best skill only if it beats base by a margin (a param). Otherwise play base.
- **Back to base when:**
  - layer 2 is unsure about the seats involved;
  - a skill's predicted responses stop matching what the seat does: track predicted against observed responses per skill and seat, and turn the skill off for that seat when they diverge beyond a param;
  - the pot has several players and no skill covers that.
- **Hysteresis:** a skill turns on at a higher confidence than it turns off. Judge skills on their predictions, never on chips won.
- **Skill contract:** each skill provides
  - `name`;
  - `applies(profile, state) -> confidence` (0 when it doesn't apply);
  - `move(profile, state, base) -> action` in the official format;
  - `assumptions(profile, state)`: the predicted responses it relies on.

  Each call runs well under a millisecond, using the standard library only.

## Build

1. Paste `model/profiler.py` and `model/fitted.py` into `bot.py` as layer 2. Replace the bot's own per-seat counters with the profiler, keeping whatever reads the bot needs that the profiler lacks.
2. Restructure the bot's decision into base, profile and picker without changing base behaviour. The current exploits move out of the base into the first two skills:
   - **Value shove:** all-in for value into seats that never fold.
   - **Bluff:** bluff seats that fold too often.

   The randomness already in the bot (size jitter, mixing near thresholds, break-even default bluffs) stays in the base.
3. Write the picker as above, with every threshold in `PARAMS`. Price every option (base and each skill that applies) by its expected chips under the opponent's full personality blend, never under its top personality alone. Choose by a softmax over those prices with a small temperature (a param): clear winners are picked almost always, and near-ties are mixed, so we stay hard to read. Never pick an option at random in proportion to the personality weights.
4. Two more skills, against extreme opponents (Owen):
   - **Call the shover:** against a seat that goes all in far more often than its hand strength allows, call with every hand whose equity against its measured shoving range beats the price. Heads-up against any two cards, that is roughly the top 35–40% of hands. Never fold to it just because the bet is big.
   - **Let the barreller bet:** against a seat that bets every street, check strong and medium hands to it and call or raise its bets; never bluff it.

   Both need the shover and the barreller to be read within a few hands: count all-ins and bets-when-checked-to directly per seat, as well as through the personality types (the types still miss the shover).

## Layer 2 fixes the picker needs

The layer 2 builder reported these. You may edit `model/` for them, rerun `fit.py`, and repaste:
- **Integration:** paste `FITTED` and the profiler code without its import block; create the profiler in `on_table_start`; call `observe_hand(summary, self.seat)` in `on_hand_end`.
- **Overconfidence:** the type posterior is untempered and reaches 1.000 within 30 hands. That would defeat "back to base when unsure". Temper it (a param) so confidence reflects real evidence, and check held-out log-loss doesn't get worse (`model/evaluate.py`).
- **Raise size:** situations don't include raise size, so an all-in shover reads as a tight type. Add a raise-size bucket (at least all-in versus not) if the value-shove skill or the shover's read needs it.
- **Simulated data:** the fitting data is already generated at `<ROOT>/.claude/worktrees/agent-a517cc6b9a8a96f4c/model/sim/` (127 MB, gitignored), where `<ROOT>` is the folder holding `notes/`. Point `fit.py` and `evaluate.py` at it instead of regenerating.

## Measure

Copy `bot.py` to `tools/baseline_bot.py` first. Report `tools/sim.py --vs tools/baseline_bot.py` (at least 24 rounds each, mean ± standard error) against:
- `kit/examples/*.py` only;
- `kit/examples/*.py` plus `kit/bot.py`;
- `kit/bot.py` only;
- `opponents/*.py`.

None may get worse beyond the error bars. Also report:
- how often each skill fired and how often the picker fell back to base, per 1,000 hands, by opponent pool;
- the ablation: base only (picker off), base plus profiler, and the full bot.

Then run `python3 team/tests/check_submission.py bot.py --kit kit` and report its lines.

## Test

Add to `tools/test_bot.py`:
- Against a seat that has called every bet, the value-shove skill fires and the bluff skill never does.
- When a skill's predicted folds stop happening, it switches off for that seat within a set number of observations.
- With no evidence, the bot plays base.
