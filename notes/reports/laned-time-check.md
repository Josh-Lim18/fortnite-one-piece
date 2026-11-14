# Own-thinking time check: report

Commit `c1ea055` on `eval/benchmark`, not pushed. It changes `tests/check_submission.py`, `tests/test_check_submission.py` and `evaluation/README.md`.

## Own thinking per 1,000 hands, lower of 2 runs (limit 0.4 s)

| Bot | First full check (load ~20) | Second full check (load ~6) |
|---|---|---|
| v1-fast | 1.39 s, fail | 0.58 s, fail |
| v1 | 1.79 s, fail | 0.41 s, fail by a hair |

On the second run, v1 came out below v1-fast.

## The 0.4 s calibration

The verdict depends on what else the laptop is running, and taking the lower of two runs doesn't remove that.

I timed both bots in alternating runs, measuring wall time and the thread's CPU time:
- v1-fast: 0.33 to 1.08 s
- v1: 0.47 to 1.63 s

In the runs where wall time matched CPU time (nothing else competing):
- v1-fast: 0.33 s
- v1: 0.47 s

That fits their settings (40 vs 60 rollouts). So on a quiet laptop, 0.4 s does separate v1-fast (pass) from v1 (fail). On this laptop today, v1-fast failed both full checks. I did not change the default.

## Not done or not verified

- The 5 s subprocess wall-time limit is unchanged. Choosing a new number would be a guess.
- The tests pass. One run failed on `kit/bot.py` in the old timeout check because of load; the rerun passed.
