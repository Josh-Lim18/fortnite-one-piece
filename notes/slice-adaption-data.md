# Slice: Adaption dataset

**Files you own:** `adaption/` (and one line in `.gitignore` for `adaption/data/`). **Time box:** 60 minutes.

We are entering a second prize: fine-tune an open-source model on the Adaption platform, ranked by win rate against the base model (SPEC.md, "Second prize"). Our dataset teaches a model to make this bot's poker decisions. Build the dataset writer.

## `adaption/make_dataset.py --examples N --out FILE --seed S`

- Plays eight-seat tables in-process with `engine.FixedHandsTable` and `engine.players.LocalPlayer` from `kit/` (put `kit/` and the repo root on `sys.path`). One seat is our bot from the repo's `bot.py`, constructed as `bot.Agent(params={"trials": 2000, "decision_ms": 2000, "round_budget_s": 1e9})` so its postflop judgement is as good as it gets; the other seats are a seeded mix of `kit/examples/*.py`, `kit/bot.py` (the organisers' starter bot) and, if any exist when you run, `opponents/*.py` (skip files without an `Agent` class, such as helpers).
- Wrap our agent so every call to `act(state)` is recorded with the action it returned, after the engine's own corrections would apply (a raise clamped to `min_raise_to`..`max_raise_to`; `all_in` when the raise equals `max_raise_to`).
- Each example is one JSON line: `{"prompt": ..., "completion": ...}`. `completion` is exactly `fold`, `check`, `call`, `all_in` or `raise <amount>`.
- The prompt is plain English a person could act on, built only from what the bot sees: a one-line statement of the game (seats, blinds, stacks), our cards, the board and street, our position by name (button, cutoff, small blind...), players still in, the pot, the price to call, the legal actions with the raise range, the action so far this hand in order, and one line per opponent still in the hand giving its profile so far this round (hands seen; how often it enters pots, raises preflop, bets or raises postflop, folds to a bet) read from the agent's own `seats` counters via `Agent._rate`. End with a fixed question asking for the action in the completion format.
- Balance the file: preflop folds are most decisions and teach little, so keep at most one in five of them; keep everything else.
- Use `multiprocessing.Pool` across tables. Print a summary: examples by street and by action.
- `--eval-share 0.1` writes a second file beside `--out` with `.eval` before the extension, split by hand so no hand appears in both.

Commit a 30-line sample as `adaption/sample.jsonl`; the full files go under `adaption/data/`, which is gitignored.

## Test

`adaption/test_dataset.py`: every line parses; every completion matches the format; a raise amount lies inside the range the prompt states; the action is among the legal actions the prompt lists; no hand is in both train and eval.

## Done

Besides the common brief: generate 12,000 examples to `adaption/data/poker.jsonl` (plus its eval file), report the summary it printed, the file sizes, how long it took, and paste two full examples (one preflop, one postflop) in the report. `scripts/verify.sh` only runs `tools/test_*.py`, so run your own test by hand and say that you did.
