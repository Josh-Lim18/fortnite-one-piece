# Poker bot

**Hackathon:** Imperial AI Hack, AI Poker Bots track, https://imperialaihack.com/pokerbots. **Deadline:** uploads close Sunday 15 November 2026, 12:00 GMT; final table 12:05. **Team:** Owen (decisions, uploads, data token); agents build.

## Pitch

A tight-aggressive no-limit hold'em bot that profiles every seat during a round and shifts its thresholds to exploit each one, with its numbers tuned offline against clones of the real field.

## Scoring

| Stage | When (GMT) | What counts | What we need |
|---|---|---|---|
| Practice | Sat 12:35–13:55 | nothing | real hands to study |
| Counted rounds | Sat 15:00–19:25 | average bb/100; only seeds Sunday's tables, which mix strong and weak | 12 rounds played, no faults |
| Bucket tables | Sun 09:00–11:55 | chips at our table, from zero | top 2 of 7–8 |
| Final | Sun 12:05 | chips over 5,000 hands, 8 bots | 1st (£500) or 2nd (£200) |

## Acceptance

Each passes on `bot.py` as uploaded.

1. `scripts/verify.sh` prints READY: one file under 200 KB, standard library only, no errors in a simulated round.
2. On the live site: zero errors, and thinking time under 5 s of the 10 s bank per round.
3. Beats every bot in `opponents/` and `kit/examples/` at an eight-seat table by a margin outside the simulator's error bars.
4. A candidate replaces the uploaded bot only after beating it in a paired-seed match in `tools/sim.py`.

## Rules of the game that shape the bot

- 7 or 8 seats, 2,000 chips every hand (100 big blinds), blinds 10/20, 1,000 hands a round, same opponents all round.
- 10 ms per decision including transport; 10 s of thinking per round; an overrun checks or folds.
- A fresh `Agent()` per round: nothing carries over, and seats are anonymous, so profiling restarts each round.
- Stacks reset each hand, so there is no survival value: take every profitable all-in.
- Organisers may switch to pot-limit or fixed-limit or cap raises; every `state` says which.

## Cut list

- Not building: solver or CFR training, neural nets, any model call, cross-round memory (impossible), a dashboard.
- Approximate by design: postflop equity is a short Monte Carlo against ranges guessed from each seat's stats.

## Stack

Python, standard library only. The bot must run on 3.12; laptops here have 3.14, so no syntax newer than 3.12. No deploy: Owen uploads `bot.py` on the track page.

## Contracts

- `bot.py`: `PARAMS` (dict of every tunable number), `Agent(params=None)` where `params` overrides entries of `PARAMS`, plus `act(state)`, `on_table_start(info)`, `on_hand_end(summary)` as in `kit/README.md`. Also `score(cards) -> int`, `card(text) -> int`, `hand_pct(c1, c2) -> float`, and `ORDER` (169 hand names, best first).
- An opponent bot is a file with a class `Agent` taking no required arguments, same three methods.
- `tools/sim.py`: `run(factories, hands, seed) -> list[int]` plays one table in-process (no subprocess, no time limit) and returns chips per seat; `compare(candidate, baseline, pool, rounds, seed) -> (mean_bb100_diff, stderr)` plays both against the same pool on the same deals. CLI: `python3 tools/sim.py bot.py other.py ... --rounds N --seed S`.
- Hand histories: `hands/*.json` as written by `kit/fetch_hands.py` (format in its docstring).
- `tools/matchups.py`: `MATCHUPS` text block and `decode(text) -> list[list[float]]`, a 169×169 table where `[i][j]` is hand `ORDER[i]`'s all-in equity against `ORDER[j]`.

## Slices

| Slice | Owner | Files | Makes real | Time box |
|---|---|---|---|---|
| Strategy and integration | orchestrator | `bot.py`, `scripts/`, `SPEC.md` | 1, 2 | ongoing |
| Simulator and tuner | agent | `tools/sim.py`, `tools/tune.py`, `tools/test_sim.py` | 3, 4 | 90 min |
| Opponent pool and hand analysis | agent | `opponents/`, `tools/analyze.py`, `tools/test_analyze.py` | 3 | 90 min |
| Preflop matchup table | agent | `tools/gen_matchups.py`, `tools/matchups.py`, `tools/test_matchups.py` | 3 | 60 min |

## Risks

| Risk | Fallback | Decide by |
|---|---|---|
| Sandbox is slower than the laptop, so rollouts time out | `trials` and `decision_ms` are params; cut them from the site's own timing figures | first practice round played |
| Uploads may stay closed from Sat 19:30 to Sunday morning | best bot uploaded by Sat 19:20 | Sat 19:00 |
| Tuned numbers overfit the clones | accept a change only if it also holds against the house bots and the previous bot | every upload |
| Organisers switch betting structure | all sizes are clamped to the legal range from `state` | n/a |

## Timeline (GMT)

- Sat 13:00: first bot uploaded (`demo-0`).
- Sat 14:45: fault-free bot live before counted rounds.
- Sat 19:20: best bot so far uploaded; Saturday's hands fetched.
- Sat night: clones fitted from Saturday's hands; tuner runs.
- Sun 08:30: strategy freeze; only numbers change after this.
- Sun 11:30: last upload. Uploads close 12:00.
