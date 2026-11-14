# Poker arena

Local bot-vs-bot arena for no-limit Texas Hold'em. [PokerKit](https://github.com/uoftcprg/pokerkit) enforces the rules; the arena seats bots, deals duplicate hands, ranks bots with confidence intervals, and replays hands in the browser.

## Setup (once per machine)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/). It fetches Python 3.11+ and every package for you.
2. Pull this branch, then `cd arena && uv run pytest`. The first run installs PokerKit and pytest into `arena/.venv`; all tests should pass.

Works on Windows, macOS and Linux. uv is set to copy files instead of hardlinking them, because hardlinks fail inside OneDrive folders.

## Quick start

```bash
cd arena
uv run arena list                                   # registered bots
uv run arena roundrobin --deals 500 --view          # heads-up duplicate match between every pair, then open the replay
uv run arena table call allin random --deals 200    # 2-9 bots at one table
uv run arena view                                   # replay the latest run in the browser
uv run pytest                                       # tests
```

Format flags: `--stack 1000 --sb 5 --bb 10` (defaults, from the organisers' brief). For the AlgoSoc kit's format use `--stack 2000 --sb 10 --bb 20`.

### Play until one bot is clearly on top

Add `--until-decided` to `table` or `roundrobin`: the arena keeps adding batches of `--deals` new deals until the leader's 95% interval clears second place's, or `--max-deals` is reached. Standings print after each batch.

```bash
# heads-up, every pair, 200 new deals per pair per batch
uv run arena roundrobin call allin random checkfold --until-decided --deals 200 --max-deals 5000
# one table, 50 new deals per batch (each played in every seating)
uv run arena table call allin random example-json --until-decided --deals 50 --max-deals 3000
```

**Time limits:** the competition allows 10 ms per decision. Only `agent` bots get that limit enforced (`time_limit_ms` in `bots.toml`); `command` bots get `timeout` (default 5 s) and in-process `python` bots none. Check the `avg ms` and `max ms` columns before trusting a slow bot's results.

The bundled bots (`checkfold`, `call`, `allin`, `random`, `example-json`) are yardsticks and examples; add your own as described under [Adding a bot](#adding-a-bot).

## How a match works

- Every hand starts each bot with `--stack` chips (stacks reset every hand).
- **Duplicate dealing:** each deal is played once per seating, so every bot plays every seat's cards. All deals are played in one seating before the seats rotate. This cancels most card luck.
- Seats follow PokerKit: with 3+ players seat 0 is the small blind, seat 1 the big blind, the last seat the button. Heads-up, seat 1 is the button and posts the small blind.
- Illegal replies are corrected (raise sizes clamped, impossible raises become calls, anything else checks if free or folds) and counted under `fixed`. Crashes and timeouts count under `errors`.

## Reading results

Each run writes `results/<time>-<command>/`:

| File | What |
|---|---|
| `leaderboard.csv` | per bot: hands, chips, **mbb/hand** (thousandths of a big blind per hand), **ci95** (±, 95% interval), fixed, errors, avg/max decision ms |
| `pairwise.csv` | round robin only: row bot's mbb/hand against column bot |
| `hands.jsonl` | every hand: players, hole cards, board, actions, payoffs |
| `run.json` | settings used |
| `viewer.html` | written by `arena view` |
| `<bot>.stderr.log` | stderr of command bots |

A difference is real only if the ± intervals don't overlap zero. Separating bots 25 bb/100 apart takes roughly 1,500 duplicate hands; 10 bb/100 apart, about 10,000.

## Adding a bot

Register it in `bots.toml`. Three kinds:

1. **`agent`**: a bot written for the AlgoSoc kit (`bot.py` with `class Agent`, `act(state)`). Put it in `bots/<name>/bot.py`. Decisions slower than `time_limit_ms` (default 10) check/fold, as on the platform.
2. **`python`**: a class in this repo subclassing `arena.bot.BaseBot` with `act(obs) -> action`.
3. **`command`**: any language. A process that reads one JSON object per line on stdin and answers each `{"type": "act", "obs": {...}}` with one JSON line. See `examples/json_bot.py`; `{python}` in the command means the arena's own Python.

### The observation (`obs`)

```json
{
  "hand_id": 12, "seat": 1, "num_players": 2, "button": 1, "players": ["a", "b"],
  "small_blind": 5, "big_blind": 10, "starting_stack": 1000,
  "street": "flop", "hole_cards": ["As", "Kd"], "board": ["Jc", "3c", "9s"],
  "pot": 60, "stacks": [970, 970], "bets": [0, 0],
  "to_call": 0, "min_raise_to": 10, "max_raise_to": 970,
  "legal_actions": ["check", "raise"],
  "history": [{"seat": 1, "street": "preflop", "action": "raise", "amount": 30}]
}
```

### The action

`{"action": "fold"}`, `{"action": "check"}`, `{"action": "call"}`, or `{"action": "raise", "amount": N}` where N is your **total bet this street** after the raise ("raise to").

After every hand all bots get `hand_over(result)` (command bots: `{"type": "hand_over", "result": {...}}`) with payoffs, board, history and `shown_cards` (hole cards of hands that reached showdown).
