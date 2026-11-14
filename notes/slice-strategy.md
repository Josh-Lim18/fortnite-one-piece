# Slice: strategy

**Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`. **Time box:** 75 minutes.

You are the only agent that edits `bot.py`, the file that gets uploaded. Read it in full first. Before changing anything, copy it to `tools/baseline_bot.py`: that is what you measure against.

## Why

Empty seats at every table are filled with the organisers' house bots (`kit/examples/`): one never folds and never raises, one picks a random legal action. Weak teams' bots behave similarly. The teams leading the practice rounds are farming those seats. In local runs the organisers' starter bot (`kit/bot.py`), which simply bets every street with any pair or jack-high, wins about +1,250 to +1,600 bb/100 against house bots where ours wins +330 to +630. On Sunday the top two by chips at each table go through, so whoever takes the most from the weak seats advances. Our bot profiles each seat but does not yet press the advantage.

## Goal 1: take the most from seats that do not fold

- Track per seat how it responds to big bets: faced one preflop and called or folded; fold-to-bet postflop already exists.
- Preflop: when seats that call big bets with wide ranges are in the pot or still to act, raise big or shove for value with every hand that has an edge against what they call with. Decide by expected chips: for each such seat, chance it calls × (2 × equity − 1) × the stack at risk, set against the stronger ranges of the seats that only call with good hands.
- Postflop: against a seat that does not fold to bets, lower the value-bet threshold towards 50% equity against its range and size up, to all-in when the edge is clear; never bluff it.
- Recognise such a seat within about 15 hands. The priors in `PARAMS` must not hide a seat that has called every bet it has faced.
- Keep it general: drive everything from the per-seat rates, not from guessing which house bot a seat is. Stacks reset every hand, so there is no reason to avoid a profitable all-in.

## Goal 2: preflop all-ins from real numbers

When `tools/matchups.py` is on `main` (run `git merge main`; another agent is building it now), paste its `MATCHUPS`, `decode` and `range_equity` into `bot.py` and replace the rough `depth = pct / width` rule for calling and making preflop all-ins with equity against the raiser's estimated range compared with the pot odds. It also gives Goal 1 its equity against a calling range. If it has not landed when Goal 1 is done and measured, use the best approximation you can build from `PCT`, say so in the report, and stop there.

## Constraints

- 10 ms per decision including transport, and 10 s of thinking per 1,000-hand round: keep the bot's own time per decision near 1 ms and its total under 3 s a round.
- An exception or an illegal action costs a hand: `act` must always return a legal action, under no-limit, pot-limit and fixed-limit (`state` gives the legal range).
- Every tunable number stays in `PARAMS`; `Agent(params=None)` keeps working (SPEC.md, Contracts). One file, standard library, under 200 KB, Python 3.12 syntax.

## Measure

`tools/sim.py` plays tables in-process; read its `--help`. Report `--vs tools/baseline_bot.py` (mean difference in bb/100 ± standard error, at least 24 rounds each) against three pools:

1. `kit/examples/*.py` only: must improve clearly.
2. `kit/examples/*.py` plus `kit/bot.py`.
3. `kit/bot.py` only (a table of starter bots): must not be worse beyond the error bars.

Then run `python3 kit/local_sim.py bot.py --rounds 2` (real time limits; the laptop is busy, so some timeouts there are noise, but errors are not) and report errors and thinking time.

## Test

`tools/test_bot.py`: after 15 hands of a seat calling every bet, the bot raises big preflop with a medium-strength hand that it would not raise big against an unknown seat; short tables under `pot_limit` and `fixed_limit` finish with zero bot errors.
