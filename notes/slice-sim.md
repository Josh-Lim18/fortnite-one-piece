# Slice: simulator and tuner

**Files you own:** `tools/sim.py`, `tools/tune.py`, `tools/test_sim.py`. **Time box:** 90 minutes.

`kit/local_sim.py` runs each bot in a subprocess under real time limits: right for a final check, too slow and too noisy for comparing two versions of a bot. Build the fast path.

## `tools/sim.py`

- Loads bot files with `importlib` (a unique module name per path, the file's folder on `sys.path` while loading) and plays them in-process with `engine.FixedHandsTable` and `engine.players.LocalPlayer` from `kit/`.
- `run(factories, hands, seed) -> list[int]`: one table; `factories` are zero-argument callables returning an agent. Seed everything that makes a run repeat: the table's `seed`, the global `random`, and each agent's `rng` attribute if it has one (seeded per seat from `seed`).
- `compare(candidate, baseline, pool, rounds, seed) -> (mean_bb100_diff, stderr)`: for each round, fill the other seats (7 of 8) from `pool` with a seeded choice and a seeded seat order, then play the same deal sequence twice, once with `candidate` in our seat and once with `baseline`. The engine shuffles one deck per hand whatever the bots do, so both plays see the same cards. The difference per round is in bb/100 (big blind 20); return its mean and standard error over rounds. Run rounds across processes with `multiprocessing.Pool`.
- CLI: `python3 tools/sim.py bot.py other.py ... --rounds N --hands 1000 --seed S [--pool opponents/*.py kit/examples/*.py]` prints bb/100 ± standard error for each named bot; empty seats are filled from the pool (default pool: `kit/examples/*.py` plus `opponents/*.py` if any exist). `--vs baseline.py` prints `compare` for the first named bot against it.

## `tools/tune.py`

Searches the numeric entries of `bot.PARAMS` (skip nested dicts, `trials`, `decision_ms`, `round_budget_s`, and anything starting `prior_`, unless named with `--keys`). Loop: perturb one to three keys of the incumbent (multiply by a log-normal factor, clamp probabilities to 0..1), run `compare(candidate, incumbent, pool, rounds, seed)`, and accept when the mean difference exceeds twice its standard error. Print each trial as one line, and write the incumbent's overrides to `notes/tuned.json` after every acceptance. Options: `--pool`, `--rounds` (default 16), `--iters`, `--keys`, `--seed`. A candidate is `lambda: bot.Agent(params=overrides)`.

## Test

`tools/test_sim.py`: chips across a table sum to zero; the same seed gives the same chips twice; `compare` of a bot against itself returns exactly 0.

## Done

Besides the common brief: report the bb/100 ± stderr that `python3 tools/sim.py bot.py --rounds 16` prints, how long it took, and one `tune.py` run of a few iterations.
