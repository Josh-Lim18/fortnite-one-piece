# Slice: opponent pool and hand analysis

**Files you own:** `opponents/`, `tools/analyze.py`, `tools/test_analyze.py`. **Time box:** 90 minutes.

Our bot is tuned against a pool of opponents, so the pool has to look like the real field: other hackathon teams' bots, many of them the organisers' starter bot or an LLM-written variation on it.

## `opponents/`

One file per bot, each with a class `Agent` (no required constructor arguments), standard library only, fast (well under 1 ms a decision, since eight play at once in the tuner).

- `starter.py`: the organisers' starter bot, same behaviour as `kit/bot.py` (expect many teams to run it nearly unchanged).
- `maniac.py`: raises and re-raises most hands, bets every street.
- `nit.py`: plays only premium hands, folds to pressure without a strong made hand.
- `shover.py`: goes all in preflop with roughly the top fifth of hands, folds the rest.
- `equity_tag.py`: what a competent team ships in an afternoon: preflop by hand rank and position, postflop by made-hand class and draws against pot odds, continuation bets, sensible sizes.
- `trapper.py`: checks and calls with strong hands, raises the river.
- `clone_base.py` with `make_agent(profile) -> class`: a bot whose behaviour is set by a stats profile (how often it enters a pot, raises preflop, re-raises, shoves, bets and raises postflop, folds to a bet; its usual bet sizes). It plays the top share of hands matching each frequency, using `ORDER` from the repo's `bot.py` for hand rank (copy the string; do not import `bot`). Clone files are `opponents/clone_<id>.py` that put their own folder on `sys.path`, import `make_agent` and set `Agent = make_agent({...})`.

## `tools/analyze.py`

`python3 tools/analyze.py hands/` reads the JSON files `kit/fetch_hands.py` saves (format in its docstring; one file per round, a `hands` list, each hand with `events`, per-seat `results`, our cards, and opponents' cards only at showdown).

No real file exists yet. The engine's own hand record (`rec` in `kit/engine/game.py`, produced with `FixedHandsTable(..., record=True)`) is the likely shape: build against that, generate sample files with it for your test, and keep every assumption about field names inside one `load_hands(path)` function so a mismatch with the real files is a one-place fix. If the round's own-seat field is missing, infer our seat as the one whose hole cards are always present.

It prints:

1. Per round and seat: hands, entered-pot rate, preflop raise rate, re-raise rate, preflop shove rate (a raise to at least 800), postflop bets and raises against checks and calls, fold-to-bet rate, how often it reached showdown, chips won, and the starting hands it showed down after a preflop all-in.
2. A leak report for our own seat: chips won and lost split by street the hand ended on, by position, and by our last action (folded, called, raised), plus our ten biggest losing hands in a readable line each.

With `--emit opponents/` it writes one `clone_<round>_<seat>.py` per opponent seat from those rates.

## Test

`tools/test_analyze.py`: play a recorded table of known bots (a calling station, `shover.py`, `nit.py`), run the analysis, and assert the rates come out where those bots' behaviour puts them (the station never raises, the shover's shove rate is near a fifth, the nit enters few pots).

## Done

Besides the common brief: report the output of `python3 kit/local_sim.py bot.py opponents/starter.py opponents/equity_tag.py opponents/maniac.py --rounds 2` so the orchestrator sees how the current bot fares against the new pool.
