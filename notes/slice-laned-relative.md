# Slice: lane D time gate relative to v1-fast

Owner: Opus subagent. Time box: 25 minutes. Decided by Owen, Sat 14 Nov 17:58 GMT.

## Why
`team/tests/check_submission.py` (branch `eval/benchmark` in the `team/` clone, commits c1ea055 and f732ccd, not pushed) gates a bot on 0.4 s of in-process thread CPU time per 1,000 hands. On this M1 (4 fast + 4 slow cores) laptop load moves the bot onto slow cores, so even CPU time reads ~1.8x high (v1-fast: 0.33 s quiet, 0.59 s at load 20). The absolute limit is also miscalibrated: v1-fast used 2.03 s of the platform's 10 s bank in real round r024, so the platform is ~6x a quiet laptop, not 10-15x.

The ratio between two bots timed under the same load holds: v1 / v1-fast is 4.1x on the busy laptop and ~4.7x on the platform.

## What to build
Replace the absolute own-thinking check with a relative one:
- `--reference PATH`: the reference bot, v1-fast. Required for the own-thinking check (no default file; the team repo has no copy and must not get one).
- Play the same seeded in-process round (the existing `own_round`) for the reference and the candidate, alternating: reference, candidate, reference, candidate. Take the lower of each bot's two totals (`act` + `on_hand_end`, thread CPU time, as now).
- Estimated platform seconds = 2.03 x candidate / reference. Fail above 5.0 s. Keep the two numbers as named constants with a one-line why (2.03 s: v1-fast in real round r024; 5 s: the team's target, half the 10 s bank).
- Error out clearly if the reference loads wrong or its total is too small to divide by.
- Print: both bots' totals and their act / on_hand_end split, the ratio, the estimated platform seconds and the limit.
- Remove `--own-limit` and the 0.4 s constant: write only the current state.
- `--hands` still scales both rounds; the ratio is scale-free.

## Files you own
`team/tests/check_submission.py`, `team/tests/test_check_submission.py`, `team/evaluation/README.md`. Nothing else. Never edit `kit/`.

## Tests
`python3 tests/test_check_submission.py --kit ../kit` from `team/` must still show: non-stdlib import, 201 KB file, act raises, slow act and slow on_hand_end all fail; `kit/bot.py` passes. Pass `kit/bot.py` as the reference in the tests where you need one. Add one case: a reference that raises makes the check fail with a clear message.

## Real check (report these numbers)
From the repo root, with `notes/bot-v1-fast.py` as the reference:
- v1-fast against itself: about 2.03 s, pass.
- v1 (`git show b0e08f2^:bot.py` into the scratchpad): about 8-10 s, fail.
- `kit/bot.py`: pass.
Report the load average next to each run.

## Done
Commit on `eval/benchmark` in `team/` as `Owen Yan <100368790+owenbonc@users.noreply.github.com>`, no co-author lines. Do not push. Write your report to `notes/reports/laned-relative.md` (repo root) and return it as your final message: commit hash, the numbers above, anything not done or not verified.
