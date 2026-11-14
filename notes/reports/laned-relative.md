# Lane D time gate relative to v1-fast: report

Commit `715645a` on `eval/benchmark` in `team/`, authored by Owen Yan, not pushed. It changes `tests/check_submission.py`, `tests/test_check_submission.py` and `evaluation/README.md`.

## What changed

- `--reference PATH` is now required (argparse). There is no default file.
- The gate plays the same seeded in-process round four times, alternating: reference, candidate, reference, candidate. Each bot's lower total counts (thread CPU time in `act` plus `on_hand_end`). Each run re-imports the bot, so module-level caches can't make its second run faster.
- Estimated platform seconds = 2.03 x candidate / reference. It fails above 5.0 s. Both numbers are named constants with a one-line why: `REFERENCE_PLATFORM_S` and `PLATFORM_LIMIT_S`.
- It fails with a clear message in three cases:
  - the reference won't import or construct `Agent`;
  - the reference raises in `act` (a raising candidate now fails the same way);
  - the reference's total is under 1 ms (`MIN_REFERENCE_S`), with a hint to pass v1-fast.
- A `--reference` that isn't a `.py` file exits before any play.
- The output prints the estimate, the ratio and the limit, then each bot's total with its act / on_hand_end split, decisions, ms a decision and both run totals.
- `--own-limit` and the 0.4 s constant are gone.

## Real check (from the repo root, `--reference notes/bot-v1-fast.py`, 1,000 hands)

| Candidate | Load average (1 min, start / end) | Candidate / reference CPU s | Ratio | Estimate | Own-thinking verdict |
|---|---|---|---|---|---|
| v1-fast (a copy of `notes/bot-v1-fast.py`) | 18.07 / 19.09 | 0.595 / 0.579 | 1.03 | 2.08 s | PASS |
| v1 (`git show b0e08f2^:bot.py`) | 19.09 / 18.54 | 2.520 / 0.579 | 4.36 | 8.84 s | FAIL |
| `kit/bot.py` | 19.83 / 18.77 | 0.019 / 0.624 | 0.03 | 0.06 s | PASS |

All three ran at the same time as each other and as the test suite, on top of the other agents' load.

## Tests

`python3 tests/test_check_submission.py --kit ../kit` (from `team/`, load ~18-19) passes. These all fail as expected: non-stdlib import, 201 KB file, act raises, slow act, slow on_hand_end, and the new case, reference act raises. `kit/bot.py` passes. `kit/bot.py` is the reference throughout. At 100 hands it thinks about 2.2-3.3 ms, above the 1 ms floor.

I also checked three cases by hand:
- a reference with no `Agent` fails with `AttributeError ... no attribute 'Agent'`;
- `kit/bot.py` as the reference at 10 hands (0.25 ms) fails as too little to divide by;
- leaving out `--reference` gives argparse's "required" error.

## Not done or not verified

- **Separate from this gate (the subprocess check, which this slice didn't change):** at load ~19 the subprocess timeout check failed v1-fast in 2 of 4 formats. Timeouts were 1.95% in fixed-limit and 1.73% in no-limit raise cap 3, against a 1% limit. So `check_submission.py` as a whole fails v1-fast on this busy laptop. That check uses wall time, so it is still load-sensitive.
- v1-fast's two runs in the same seeded round made different numbers of decisions (1430 vs 1440). The bot doesn't play exactly the same way twice, so "same round" is close but not identical. The ratio still came out at 1.03.
- I didn't check the ratio on a quiet laptop. I didn't run `scripts/verify.sh` either: it belongs to the root repo, not `team/`.
