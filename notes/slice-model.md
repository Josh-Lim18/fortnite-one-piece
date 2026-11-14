# Slice: layer 2 opponent model, fitted offline

**Files you own:** `model/` (new). **Time box:** 90 minutes. Do not edit `bot.py`: another agent is changing it now. Your online profiler plugs into it afterwards.

Layer 2 is Owen's, and sits on the base strategy (SPEC.md, "Strategy"; the three layers are on the team's Notion brief). It predicts, for each opponent seat before it acts, the chance it folds, calls or raises, and what hands it holds after each action. The bot starts every round fresh, with no memory, so learning happens offline: fit constants on recorded hands, paste them into `bot.py`, and update them online during the round.

## Data

- **Simulated, now:** play recorded tables with `engine.FixedHandsTable(..., record=True)` from `kit/`. Fill seats with known bots: `kit/examples/*.py`, `kit/bot.py` and `opponents/*.py` (skip helper files without an `Agent`). Because we know each seat's bot, we can check the model recovers it. Generate enough rounds to fit and to hold some out, split by round.
- **Real, later:** the files `kit/fetch_hands.py` saves. Reuse the loader in `tools/analyze.py` (`load_hands`), so a mismatch with the real format is fixed in one place. The format is unverified until Owen's data token arrives. Build against the engine's own record shape.

## Build

1. **`model/dataset.py`:** turns hands into one row per opponent decision. Each row holds the seat, its round, hand number, street, position, players in, whether it faces a bet, the bet's size as a share of the pot (buckets: none, under 0.35, 0.35–0.8, 0.8–1.3, over 1.3), how many raises this street, the action taken, and, when the seat reached showdown, its hole cards and the board.
2. **`model/fit.py`:** writes `model/fitted.py`, a constants block of plain literals small enough to paste into `bot.py` (aim under 30 KB). It fits:
   - **Priors:** population rates for each situation cell, and how much seats really differ (empirical Bayes: compare the spread of per-seat rates with the spread sampling noise alone would give). That sets the prior's weight in hands.
   - **Types:** cluster seats on their stat vectors into a few types (k-means, k chosen by held-out score, about 4–6). Each type has a full table of action probabilities per situation cell.
   - **Ranges:** for each type, street and last action, the distribution of showdown hand strength. Use preflop hand percentile from `bot.ORDER` preflop, and the hand's percentile against all hands on that board postflop, in about 10 buckets. Showdown hands are a biased sample: say so in the output, and shrink sparse cells toward the type's overall distribution.
3. **`model/profiler.py`:** the online model, pure standard library, to be pasted into `bot.py` beside `fitted.py`. Methods:
   - `observe(...)` for each action seen.
   - `observe_showdown(...)`.
   - `predict(seat, situation) -> (fold, call, raise)`.
   - `type_posterior(seat)`.
   - `range(seat, street, action) -> bucket distribution`.

   A seat's prediction blends, by evidence weight, its own counts with its type mixture and with the population prior. Older observations fade (half-life as a constant, near 150 hands). Each update and prediction must take well under 0.2 ms.
4. **`model/evaluate.py`:** on held-out rounds, replay each round through a fresh profiler and score every opponent action by the log-loss of the probability predicted just before it. Print log-loss by hands seen (buckets 0–25, 25–100, 100–300, 300+) for three versions: prior only; per-seat counts with the prior; full model with types. Also print how often a seat's top type matches its true bot, by hands seen.

## Test

`model/test_model.py`:
- The full model beats prior-only on held-out log-loss.
- `kit/examples/calling_station.py` seats are assigned a type that almost never folds within 30 hands.
- Predictions are valid probabilities.
- `fitted.py` stays under 30 KB.

## Done

Besides the common brief: report the evaluate table, the type recovery numbers, the fitted file's size, the profiler's time per update, and what changes when real hand files arrive.
