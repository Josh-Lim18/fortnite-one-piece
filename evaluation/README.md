# Evaluation (lane D)

Which candidate bots actually beat the incumbent, and which would fail on upload. Python standard library only.

Every tool needs the organisers' starter kit (the engine). It looks for `kit/` at the repo root; pass
`--kit PATH` to point anywhere else. Without it, the tool stops and says so.

## Commands

```bash
python3 tests/check_submission.py bot.py --reference v1-fast.py   # the gate before any upload
python3 evaluation/run.py --incumbent kit/bot.py cand.py [more.py ...] --rounds 32 --seed 1   # development
python3 evaluation/run.py --incumbent kit/bot.py cand.py --final                             # held-out seeds
python3 evaluation/aggregate.py                                # one table per incumbent, with verdicts
python3 evaluation/analyze.py hands/                           # hand histories saved by kit/fetch_hands.py
python3 evaluation/analyze.py hands/ --emit evaluation/opponents/   # also write a clone bot per opponent seat

python3 tests/test_run.py               # deals repeat, chips sum to zero, a bot vs itself is exactly 0
python3 tests/test_check_submission.py  # the gate fails broken or slow bots or a broken reference, passes kit/bot.py
python3 tests/test_analyze.py           # analyze.py reads known bots' habits back; the pool plays clean
```

## The verdict rule

A candidate is **better** only when, on the held-out seeds (`run.py --final`), its paired difference from the
incumbent is above twice its standard error. Anything else, including any result on development seeds, keeps
the incumbent. Tune on development seeds (`--seed`); `run.py` refuses any seed listed in `holdout_seeds.txt`
unless given `--final`. Every look at the held-out seeds spends a little of their honesty, so run `--final`
only on a candidate you would ship.

## What each part does and does not prove

- **`tests/check_submission.py`** checks the file is at most 200,000 bytes, parses as Python 3.12, imports only
  the standard library (by `sys.stdlib_module_names` under 3.12; a relative import or a sibling module fails),
  and has a top-level `class Agent`. It re-runs itself under Python 3.12 through `uv`, imports the file and
  constructs `Agent()` in the kit's subprocess player, then plays one round in each format (no-limit,
  pot-limit, fixed-limit, no-limit with a raise cap of 3) with the real limits: 10 ms a decision, 10 s bank a
  round. It fails on any error, timeouts above 1% of decisions, any bank-out, or more than 5 s of thinking in a
  round (subprocess wall time, transport included). Then it times the bot's own thinking in-process, transport
  excluded, against `--reference` (required: v1-fast, whose platform time is known; the repo holds no copy).
  Both play the same seeded no-limit round at a 7-seat table against the kit's example bots and `kit/bot.py`,
  alternating reference, candidate, reference, candidate, each time summing the thread's CPU time
  (`time.thread_time`) in `act` and `on_hand_end`. The lower of each bot's two totals counts. The estimate is
  2.03 s (v1-fast's own thinking in real round r024) times candidate / reference, and it fails above 5 s (the
  team's target, half the 10 s bank). It prints both totals with their act and on_hand_end split, the ratio,
  the estimate and the limit, and fails clearly when the reference won't load, raises in `act`, or thinks under
  1 ms. Laptop seconds swing about 1.8x with load (busy cores push the bot onto the M1's slow cores), but two
  bots timed back to back under the same load keep their ratio, and `--hands` scales both rounds alike. It does
  **not** prove the bot is safe in the sandbox: that is one CPU core, 512 MB and a sealed container, and this
  laptop is none of those. It does not check memory, CPU use between turns, or behaviour against opponents other
  than the house bots.
- **`evaluation/run.py`** plays each round once per bot (incumbent first) at the same table: same deck seed,
  same opponents drawn from the pool by the round's seed, same seat (rotating with the round), and the same
  random seeds for every bot's `rng`. The paired difference cancels most of the card luck, so its standard
  error is much smaller than the raw bb/100 spread. It runs in-process for speed: timeouts count decisions
  slower than 10 ms and bank-outs count rounds over 10 s, but nothing is cut off, and timing on a loaded
  laptop with parallel workers is noisy. It only proves a candidate beats the incumbent **against this pool**;
  the real tables are other teams' bots and the house bots, so a pool that misses a style can mislead.
- **`evaluation/results/`** holds one JSON record per run (never appended to): each bot's path and sha256, the
  engine revision (a hash of `kit/engine/*.py`), opponents and their hashes, seeds, seats, hands, settings, and
  per bot chips, bb/100, the paired difference with its standard error, errors, timeouts, bank-outs and
  thinking time, plus every round.
- **`evaluation/aggregate.py`** pools rounds across records only when the incumbent, candidate (by hash),
  engine, opponent pool and hands per round all match; a repeated seed and seat is the same deal and counts
  once.
- **`evaluation/opponents/`** is the benchmark pool: a starter-bot copy, a nit, a maniac, a shover, a trapper,
  an equity-based tight-aggressive bot, and `clone_base.py` (the shared hand reading, and a bot driven by a stats
  profile). They are guesses at what other teams ship, not real opponents.
- **`evaluation/analyze.py`** reads the round files `kit/fetch_hands.py` saves: per-seat statistics, a leak
  report for our seat, and with `--emit` a clone bot per opponent seat. No real file exists yet, so every
  assumption about their shape lives in `load_hands()`, which stops with the file's actual keys when a guess is
  wrong. Our seat is inferred when the file doesn't say; the clones only roughly match postflop habits.
