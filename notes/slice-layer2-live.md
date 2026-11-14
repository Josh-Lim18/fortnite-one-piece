# Slice: fuller layer 2 inside v1-fast (the live bot)

**Base:** local branch `poker-live` (commit b0e08f2; `bot.py` is v1-fast, live as Joca v4). **Your branch:** `layer2/live`. **Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`. **Time box:** 75 minutes; report by about 18:50. Uploads close at 19:30 tonight and reopen Sunday 09:00.

## Goal

v1-fast already has a simple layer 2. The `Seat` counters (vpip, pfr, shove, bets, passive, folds, continues) start from `prior_*` guesses, are read through `Agent._seat(i)` and `Agent._rate(count, total, prior)`, and are updated in `on_hand_end`. Replace what those calls return with a fuller opponent model. Leave the base's decision logic (layer 1) exactly as it is: Anh owns it and is fixing it on his own branch, and the read calls are the contract between his layer and yours. Keep every call site's name and meaning, so his fixes merge cleanly.

## The fuller model

Port the ideas from the layer 2 model in `model/` on `main` (`model/profiler.py`, `model/fitted.py`, `notes/slice-model.md`), cheaply:
- **Personalities.** Several fitted types, each with action rates by situation. Keep a per-seat type posterior, updated incrementally: for each observed action, add that type's log-probability for the action, so each action costs O(types). Temper it as `model/` does (`TEMPER`).
- **Blended rates.** Each rate the base reads (entering pots, preflop raise, shove, postflop aggression, fold to a bet) becomes a blend of three things: the seat's own decayed counts, the personality mixture, and the population prior, weighted by evidence.
- **Fading.** Old observations fade, with a half-life as a param, near 150 hands.
- **Random or strategic (cheap version).** At showdown, compare the shown hand's preflop strength (`hand_pct`, no simulation) after the seat raised with after it only called. A seat whose raises don't predict stronger hands gets wider ranges.
- **Constants.** Use the fitted constants from `model/fitted.py`. A refit on real tournament hands may land on `main` while you work, from the real-data analysis. If `git log main -- model/fitted.py` shows a newer commit than when you started, pull that `fitted.py` in before measuring, and say which you used.

## Time budget (hard)

The tournament machine is 10–15x slower than this laptop. v1 ran its 10 s round bank out at about 0.6 s of laptop thinking per round; v1-fast uses about 0.2 s. Your additions must keep the whole bot's own thinking per round within 1.5x v1-fast's, measured in-process back to back on the same deals (`Agent.spent`). Work in `on_hand_end` counts too, because it delays the next reply, so time it and include it. No Monte Carlo inside layer 2. The laptop is shared with other agents, so measure as ratios run back to back.

## Measure

Copy v1-fast's `bot.py` to `tools/baseline_bot.py` first. Report `python3 tools/sim.py bot.py --vs tools/baseline_bot.py --rounds 32` (mean ± standard error) with `--pool kit/examples/*.py`, with `--pool kit/bot.py`, and with `--pool opponents/*.py`. If `opponents/real/` clones exist on `main` by then (the real-data analysis is building them), add `--pool` with those too and weight that result most. Then run lane D's check: `python3 "<ROOT>/team/tests/check_submission.py" bot.py --kit kit`, where `<ROOT>` is the folder holding `notes/`. Report its lines and the thinking-time ratio.

## Test

Add to `tools/test_bot.py`:
- a seat that has called every bet for 30 hands reads as a non-folder through `_rate`;
- a seat whose raises show weak hands at showdown gets a wider range;
- `on_hand_end` plus `act` time per hand stays within budget.

## Done

Commit on `layer2/live`. Never push. Final message (under 300 words):
- the comparison table;
- the check lines;
- the thinking-time ratio;
- which `fitted.py` you used;
- a one-line verdict: upload or not, by the team rule that a change goes in only if it wins by more than twice its standard error somewhere and loses nowhere beyond the error bars.
