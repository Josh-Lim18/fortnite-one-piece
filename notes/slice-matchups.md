# Slice: preflop matchup table

**Files you own:** `tools/gen_matchups.py`, `tools/matchups.py`, `tools/test_matchups.py`. **Time box:** 60 minutes.

The bot decides preflop all-ins from a rough rule. Replace the guess with numbers: the all-in equity of every starting-hand class against every other, small enough to paste into the 200 KB `bot.py`.

## `tools/gen_matchups.py`

- For each pair of the 169 classes in `bot.ORDER` (i < j), estimate by Monte Carlo the equity of class i against class j all in preflop, ties counting half: each trial picks concrete cards for both hands that do not collide (suits at random among the legal ones), deals five board cards, and compares `bot.score`. The mirror entry is one minus it; the diagonal comes from its own trials (it is not exactly 0.5 only through ties, so 0.5 is fine there).
- Aim for a standard error near 0.01 per entry (about 2,500 trials). Use `multiprocessing.Pool`; say in the report how long the full run took.
- Writes `tools/matchups.py`.

## `tools/matchups.py` (generated, committed)

- `MATCHUPS`: the upper triangle as text, one byte of precision per entry (equity × 255, rounded), encoded so the whole file stays under 40 KB (`base64.b85encode` of the bytes is fine).
- `decode(text) -> list[list[float]]`: the full 169×169 table.
- `range_equity(table, weights, i, width) -> float`: equity of hand `i` against a range made of the best `width` share of all starting hands, each class weighted by its number of card combinations (6 pairs, 4 suited, 12 offsuit; `weights` is that list in `ORDER` order), the last class counted fractionally so the result moves smoothly with `width`.

The orchestrator pastes `MATCHUPS`, `decode` and `range_equity` into `bot.py`, so they must depend on nothing but the standard library and `ORDER`.

## Test

`tools/test_matchups.py`: AA against KK is 0.80–0.84; AKs against QQ is 0.44–0.48; 72o against AA is 0.10–0.14; `table[i][j] + table[j][i]` is 1 within rounding; `range_equity` of AA against any width is above 0.8 and of 72o against the top 5% is under 0.25; `decode` takes under 50 ms.

## Done

Besides the common brief: report the file size of `tools/matchups.py` and `range_equity` for QQ, AKo, 99, AJs and KQo against widths 0.03, 0.10, 0.25 and 0.55.
