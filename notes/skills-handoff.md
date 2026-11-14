# Skills handoff (for Colin and his coding agent)

You are adding skills to layer 3 of the team's poker bot. Owen built layers 1–3 and the first five skills. Your job is to grow the skill library, one tested skill per PR.

## Where things are

- **Branch:** `poker/bot` of `Josh-Lim18/fortnite-one-piece`. Branch off it (for example `skills/overbet`) and open each PR into `poker/bot`. Owen reviews: nobody reviews their own changes.
- **The bot:** `bot.py`, one file and the only thing that gets uploaded.
  - Layer 1, the base strategy: `_preflop`, `_postflop`.
  - Layer 2, the opponent model: `Profiler`, plus its fitted constants `FITTED`.
  - Layer 3: the skill classes and `SKILLS` tuple (search for "layer 3"), and the picker `Agent._pick`.
- **Read first:**
  - `SPEC.md`, section "Strategy";
  - the team's Notion page "Poker Bot — Team operating brief", sections "Layer 3: the autopicker and the skill contract" and "Skill library: how to add a skill";
  - `notes/slice-picker.md`: how the picker and the first five skills were specified.
- **The organisers' kit:** `kit/`, unchanged. The engine, house bots and `local_sim.py` are there.

## The skill contract

A class with a `name` and three static methods:

| Method | Returns |
|---|---|
| `applies(bot, state)` | confidence 0–1; 0 means the skill doesn't apply |
| `move(bot, state, base)` | an action dict, or `None` to pass |
| `assumptions(bot, state)` | a list of `(seat, kind, predicted)`, with `kind` one of `FOLD`, `CONT`, `BET` |

Add the class to `SKILLS`. The picker prices your move against the base move using layer 2's predictions. It plays your move only when it beats base by `pick_margin` of the pot, and picks among near-ties at random. Once your assumptions stop holding for a seat, it switches your skill off for that seat.

Helpers:
- `bot.ctx`: the current spot (`live`, `pre`, `street`, `j`, `multi`, and more).
- `bot._read(seat, cell, kind)`: layer 2's prediction and its confidence.
- `bot._cell_for(state, raise_to, seat)`: the situation a seat would face if we raised to that amount.
- `bot._base_size(state)`: the standard bet size.
- `bot._raise(state, amount)`: a legal raise with jitter.

Copy the pattern of an existing skill: `Bluff` is the simplest.

## Rules

- Each method runs well under a millisecond; the whole decision has 10 ms, including transport.
- Standard library only, Python 3.12 syntax, and `bot.py` stays under 200 KB (it is about 86 KB now).
- Every tunable number goes in `PARAMS`.
- Bet sizes depend on the spot and the opponent, never on our own hand.

## Skills not built yet (pick one per PR)

1. **Thin value:** a tiny bet (about 0.1–0.33 pot) with medium hands against seats that call too much.
2. **Overbet:** 1.7–3 times the pot against seats that call on a fixed equity cutoff whatever the size (`opponents/` has none yet; add `opponents/threshold.py` to test it).
3. **Check-raise:** check strong hands and some bluffs to a seat that bets whenever it's checked to, then raise.
4. **Light re-raise:** re-raise preflop against a raiser that folds to re-raises too often.
5. **Barrels:** a second and third bet against seats that fold to repeated bets.

## Done means

1. `python3 tools/test_bot.py` passes, including your new test: the skill fires where it should and not where it shouldn't.
2. Copy `bot.py` to `tools/baseline_bot.py` before your change. Then run `python3 tools/sim.py bot.py --vs tools/baseline_bot.py --rounds 24` with `--pool kit/examples/*.py`, `--pool kit/bot.py` and `--pool opponents/*.py`. No pool may be worse beyond the error bars, and the pool your skill targets should improve.
3. `scripts/verify.sh` prints READY.
4. Lane D's `tests/check_submission.py bot.py --kit kit` (team repo PR #4, branch `eval/benchmark`) passes every line.
5. The PR body gives those numbers and how often the skill fired per 1,000 hands (`Agent.stats`).

## Current state (Sat 15:50)

- Against the earlier bot on the same deals this version is not yet better (within noise; −11 ± 8 bb/100 against `opponents/`), so it is not the upload. The live upload is v1.
- Known gaps: preflop isn't priced by the picker yet; "call the shover" isn't tracked against what happens; pots with several players use only the value shove.
- The opponent model is fitted on simulated bots only. Refitting on real hands needs the team's data token: `python3 model/fit.py hands/`.
