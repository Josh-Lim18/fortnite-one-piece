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

## Second prize: Best Use of Adaption

Open to every team on top of its main track ($1,000 credits each, plus merch). The rule on the event site: "Fine-tune a model with Adaption. Ranked on Adaption's leaderboard by win rate against the base model." Extra prizes are shown in a live presentation to judges (Sun 13:00–16:30) and need a Devpost submission with a public GitHub repo by Sun 12:00.

Our entry: an open-source model fine-tuned on Adaption to make this bot's poker decisions. Each training example is one decision: the prompt describes the hand as text (cards, board, position, pot, price, action so far, each opponent's profile), and the answer is the action our bot takes when given unlimited thinking time. The fine-tuned model cannot run in the tournament sandbox; it is a separate deliverable that reuses the bot and the engine.

## Acceptance

Each passes on `bot.py` as uploaded.

1. `scripts/verify.sh` prints READY: one file under 200 KB, standard library only, no errors in a simulated round.
2. On the live site: zero errors, and thinking time under 5 s of the 10 s bank per round.
3. Beats every bot in `opponents/` and `kit/examples/` at an eight-seat table by a margin outside the simulator's error bars.
4. A candidate replaces the uploaded bot only after beating it in a paired-seed match in `tools/sim.py`.
5. Adaption: a fine-tune of our dataset has finished on the platform and shows on its leaderboard; the README says what was trained, on what, and what is not measured.

## Rules of the game that shape the bot

- 7 or 8 seats, 2,000 chips every hand (100 big blinds), blinds 10/20, 1,000 hands a round, same opponents all round.
- 10 ms per decision including transport; 10 s of thinking per round; an overrun checks or folds.
- A fresh `Agent()` per round: nothing carries over, and seats are anonymous, so profiling restarts each round.
- Stacks reset each hand, so there is no survival value: take every profitable all-in.
- Organisers may switch to pot-limit or fixed-limit or cap raises; every `state` says which.

## Time budget (decided Sat 18:00)

Measured: v1 used 9.11, 9.87 and 10.03 s of the 10 s round bank, and the last round ran out with 41 forced check/folds. v1-fast used 2.03 s (round r024), about 6x its 0.33 s of thread CPU time on a quiet laptop. Laptop load moves the bot onto the M1's slow cores, so absolute laptop times read high; the ratio between two bots timed under the same load holds (v1 / v1-fast: 4.1x busy laptop, ~4.7x platform).

- **Target:** at most 5 s of the 10 s bank on the platform. Lane D's check times the candidate and v1-fast alternately in-process (thread CPU time in `act` plus `on_hand_end`, one seeded 1,000-hand round each), estimates platform seconds as 2.03 × candidate ÷ v1-fast, and fails anything above 5 s. On a quiet laptop that is about 0.8 s of the bot's own thinking.
- **Split:**
  - layer 1 (base, including equity) at most 60%;
  - layer 2 (profiling, mostly `on_hand_end`) at most 15%, with incremental updates only and no Monte Carlo;
  - layer 3 (picker) at most 25%, with at most 3 candidate moves priced per decision, priced only heads-up, cheapest checks first, and one equity estimate reused across sizes.
- **Equity:** the equity network replaces the Monte Carlo (0.57x the time, mean error 0.026 vs 0.080, no +5-point bias), once ported onto `poker/live` after Anh's fixes.
- **Time governor:** the bot compares its own thinking so far with its pace for the hands played. Past 1.2x pace it prices fewer picker candidates. Past 1.5x pace it plays the base move only. Past the hard floor (`round_stop_s`) it uses the cheapest estimate. Every step down is a param.
- **Check after every upload:** download the next round and read `think_s`. Above 6 s, cut the budget.

## Strategy

- Baseline: tight-aggressive preflop from hand rank and position; postflop from Monte Carlo equity against ranges estimated per seat, compared with pot odds.
- Every assumption about an opponent is adaptive: it comes from that seat's measured behaviour this round, shrunk toward a table-wide or prior rate while evidence is thin, decayed so a change of style is re-read, and capped so a wrong read costs little.
- Exploits, each used against a seat only while its measured responses say it profits: wide value bets and all-ins against seats that don't fold; bet sizes chosen from the seat's response curve, from tiny bets to overbets, and with strong hands a multi-street plan (the same pot fraction each street, all in by the river) priced against shoving now; barrels against seats that fold to repeated bets; check-raises against seats that bet when checked to; light re-raises against raisers that fold to them; exact-range reads of bots whose bet-size formula fingerprints them.
- Our bet size on a street never depends on bluffing or hand strength, and carries small random jitter.
- Not doing: deliberate mid-round style switches.

## Cut list

- Not building: solver or CFR training, neural nets, any model call, cross-round memory (impossible), a dashboard.
- Approximate by design: postflop equity is a short Monte Carlo against ranges guessed from each seat's stats.

## Stack

Python, standard library only. The bot must run on 3.12; laptops here have 3.14, so no syntax newer than 3.12. No deploy: Owen uploads `bot.py` on the track page.

## Contracts

- `bot.py`: `PARAMS` (dict of every tunable number), `Agent(params=None)` where `params` overrides entries of `PARAMS`, plus `act(state)`, `on_table_start(info)`, `on_hand_end(summary)` as in `kit/README.md`. Also `score(cards) -> int`, `card(text) -> int`, `hand_pct(c1, c2) -> float`, and `ORDER` (169 hand names, best first).
- An opponent bot is a file with a class `Agent` taking no required arguments, same three methods.
- `tools/sim.py`: `run(factories, hands, seed) -> list[int]` plays one table in-process (no subprocess, no time limit) and returns chips per seat; `compare(candidate, baseline, pool, rounds, seed) -> (mean_bb100_diff, stderr)` plays both against the same pool on the same deals. CLI: `python3 tools/sim.py bot.py other.py ... --rounds N --seed S`.
- `adaption/make_dataset.py --examples N --out FILE --seed S`: writes one JSON object per line with `prompt` and `completion`; `completion` is `fold`, `check`, `call`, `all_in` or `raise <amount>`.
- Hand histories: `hands/*.json` as written by `kit/fetch_hands.py` (format in its docstring).
- `tools/matchups.py`: `MATCHUPS` text block and `decode(text) -> list[list[float]]`, a 169×169 table where `[i][j]` is hand `ORDER[i]`'s all-in equity against `ORDER[j]`.

## Slices

| Slice | Owner | Files | Makes real | Time box |
|---|---|---|---|---|
| Integration | orchestrator | `scripts/`, `SPEC.md`, merges | 1, 2 | ongoing |
| Simulator and tuner | agent | `tools/sim.py`, `tools/tune.py`, `tools/test_sim.py` | 3, 4 | 90 min |
| Opponent pool and hand analysis | agent | `opponents/`, `tools/analyze.py`, `tools/test_analyze.py` | 3 | 90 min |
| Adaption dataset | agent | `adaption/` | 5 | 60 min |
| Preflop matchup table | agent | `tools/gen_matchups.py`, `tools/matchups.py`, `tools/test_matchups.py` | 3 | 60 min |
| Bot: exploit non-folders, matchup all-ins | agent, then the next two in order | `bot.py`, `tools/test_bot.py` | 3 | 75 min |
| Bot: bet-size reads, robust profiling | agent | `bot.py`, `tools/test_bot.py`, `opponents/switcher.py` | 3 | 75 min |
| Bot: adaptive pressure moves | agent | `bot.py`, `tools/test_bot.py`, `opponents/threshold.py` | 3 | 90 min |

## Risks

| Risk | Fallback | Decide by |
|---|---|---|
| Sandbox is slower than the laptop, so rollouts time out | `trials` and `decision_ms` are params; cut them from the site's own timing figures | first practice round played |
| Uploads are closed from Sat 19:30 to Sun 09:00 | best bot uploaded by Sat 19:20 | Sat 19:00 |
| An Adaption fine-tune takes hours, or its data format differs from ours | start it Saturday afternoon; the dataset writer is one command to rerun in another format | Sat 16:00 |
| Tuned numbers overfit the clones | accept a change only if it also holds against the house bots and the previous bot | every upload |
| Organisers switch betting structure | all sizes are clamped to the legal range from `state` | n/a |

## Timeline (GMT)

- Sat 13:00: first bot uploaded (`demo-0`).
- Sat 14:45: fault-free bot live before counted rounds.
- Sat 16:00: Adaption dataset ready; Owen starts the fine-tune.
- Sat 19:20: best bot so far uploaded (it plays Sunday's first rounds; uploads reopen Sun 09:00); Saturday's hands fetched.
- Sat 21:00: building closes; work continues remotely.
- Sat night: clones fitted from Saturday's hands; tuner runs.
- Sun 08:30: strategy freeze; only numbers change after this.
- Sun 11:30: last upload. Uploads close 12:00.
- Sun 11:45: Devpost submitted, repo public. Submissions close 12:00.
- Sun 13:00–16:30: Adaption presentation to judges.
