# Equity network and time governor in the live line: report

Branch `equity/live`, from `layer2/live` at `3d03277`. Commits: `a44ae51` (network, governor, tests), then this report.

## What changed

- `equity_net/` copied from `main` unchanged (`git checkout main -- equity_net/`). `bot.py` carries its encoder, inference and weights byte for byte: the sources of `net_features`, `net_load` and `net_forward` match `equity_net/`, and `NET_WEIGHTS` matches `weights.txt`. Checked without torch, since `equity_net/test_net.py` imports it. AA against one random hand reads 0.852.
- `PARAMS["equity_net"] = True`. With it on, `Agent._equity` asks the governor which step it is on. Step 0 is the network; steps 1 to 3 are the Monte Carlo loop with fewer rollouts. With it off, the Monte Carlo path is v1-fast's, unchanged: 40 trials, `round_budget_s`, `round_stop_s`, the 0.6 ms deadline and `if t & 3`. The loop itself is untouched. The only change there is that its `trials =` line moved into an `else`, so Anh's fixes merge with at most a one-line conflict.
- `Agent._governor()`: the pace is `round_target_s × (hands ended + 1) / hands in the round`, with the round length taken from `on_table_start`'s `hands` (1,000 if missing or None). It compares `self.spent` (act plus on_hand_end, perf_counter) against that pace.

## Governor steps and their costs

| Step | When | Equity estimate | Per query, thread CPU | MAE vs 4,000-sample truth | Bot thinking per 1,000 hands |
|---|---|---|---|---|---|
| 0 | on pace | network | 235 µs (1.00x) | 0.026, signed −0.006 | 0.680 s (1.00x) |
| 1 | past `slow_pace` 1.2x pace | 10 rollouts (`slow_trials`) | 72 µs (0.31x) | 0.148, signed +0.052 | 0.543 s (0.80x) |
| 2 | past `slower_pace` 1.5x pace | 6 rollouts (`slower_trials`) | 46 µs (0.19x) | 0.193, signed +0.065 | 0.524 s (0.77x) |
| 3 | past `round_stop_s` 2.5 s | 3 rollouts (`stop_trials`) | 25 µs (0.11x) | 0.263, signed +0.056 | 0.498 s (0.73x) |
| network off | | v1-fast's 40 rollouts | 265 µs (1.13x) | 0.093, signed +0.051 | 0.724 s (1.06x) |

Per query: 1,352 postflop positions from `equity_net/gen_data.py --positions 1500 --samples 4000 --seed 9001`, every estimate timed back to back on each position, load average 8.6. Bot thinking: `tools/test_bot.thinking` over 4 seeds × 250 hands against kit/examples, run in both orders, at load 7–13. On the same runs v1-fast took 0.683 s and layer 2 took 0.699 s. Every threshold, rollout count and the target is a param: `round_target_s` 5.0, `slow_pace`, `slow_trials`, `slower_pace`, `slower_trials`, `round_stop_s`, `stop_trials`.

**On the laptop it never fired.** Over 4 seeded 1,000-hand rounds against kit/examples plus kit/bot.py at load 40, all 1,150 equity calls were at step 0. Own thinking was 0.27–0.44 s a round (perf_counter), against a pace of 5 s and a hard floor of 2.5 s.

## Gate

- `scripts/verify.sh`: **READY** (rules, test, sim, secrets), twice: at load 14 and at load 44. One run in between, at load 34, failed `tools/test_matchups.py`'s 50 ms wall-time limit on `matchups.decode`. That code and test are not part of this change, and the test passed three times in a row straight after.
- Governor tests in `tools/test_bot.py`, both pass. The first forces `spent` and `hand` and counts rollouts by wrapping `rng.sample`. On pace it runs 0 rollouts and returns exactly the network's value, at 1.1x pace still 0, at 1.3x pace 10, at 1.6x pace 6, past `round_stop_s` 3, and with the network off 40. The second plays a 150-hand table with each step forced by params (`round_target_s` 1e-9, `slower_pace` 1e9, `round_stop_s` 0). It asserts 0 errors without act's safety net, and that the governor ends on the forced step.
- Lane D's check (`team/tests/check_submission.py bot.py --kit kit --reference notes/bot-v1-fast.py`, main checkout's copies): size 63,682 B, standard library only, Agent found, loads under Python 3.12.16, all PASS. Every round had 0 errors and 0 bank-outs. I ran it five times, alternating with layer 2 to see the load effect:

| Run | Load average | Bot | Own thinking on the platform (ratio to v1-fast) | Timeouts: no_limit / pot_limit / fixed_limit / raise cap 3 |
|---|---|---|---|---|
| 1 | 12.6 → 19.4 | candidate | **2.13 s** (1.05) | 0.49% / 0.65% / **1.55% FAIL** / 0.14% |
| 2 | 26.2 | layer 2 | 2.20 s (1.09) | 0.72% / **1.00% FAIL** / **3.27% FAIL** / **1.47% FAIL** |
| 3 | 51.7 | candidate | **2.28 s** (1.12) | 0.00% / 0.26% / **1.09% FAIL** / 0.07% |
| 4 | 66.5 | layer 2 | 2.00 s (0.99) | 0.22% / 0.20% / 0.05% / 0.00% |
| 5 | 74.6 → 58.0 | candidate | **1.71 s** (0.84) | 0.86% / 0.46% / 0.17% / 0.13% |

  The own-thinking estimate is well under 5 s every time. Against layer 2's 2.04 s the candidate averages 2.04 s (1.71–2.28), and layer 2 averages 2.10 s here. The two are within the check's run-to-run swing, so the candidate is not proven cheaper. In `test_bot.thinking`, run back to back, it is 0.75–0.91x layer 2 (0.91x with layer 2's Monte Carlo deadline lifted so load cannot clip it). The timeout FAILs are wall time at load 12–75. Layer 2 fails more of them on the same laptop, and the run at load 75 passes all four. Worst decisions were 15–62 ms, also wall time.
- Same deals against `layer2/live` (3d03277), `tools/sim.py --vs`, seed 1, bb/100:

| Pool | Rounds | candidate − layer 2 |
|---|---|---|
| opponents/real (from main) | 128 | **+10.7 ± 2.6** |
| kit/examples | 32 | −33.2 ± 32.8 |
| kit/examples | 128 | +14.2 ± 18.1 |
| kit/bot.py | 32 | +1.3 ± 2.5 |

The 32-round kit/examples result sits 0.4 bb/100 beyond one standard error. The 128-round run on the same seed, whose first 32 rounds are those deals, is +14.2 ± 18.1, so that was random_bot variance. No pool loses beyond its error bars at 128 rounds. The sims ran at load 3–14. Under load the Monte Carlo's 0.6 ms wall-time deadline cuts layer 2's rollouts, while the network has no deadline. Part of the gain may come from that, and the platform's single core may see the same.

## Not done, not verified, and what I'd do differently

- **The network saves little time here.** Its 0.57x was measured against main's Monte Carlo (60 trials, 1.5 ms). Against v1-fast's (40 trials, 0.6 ms) it is 0.89x in thread CPU per query. `equity_net/measure.py`, which times in wall time at load 12.8, puts it at 1.15x, because the Monte Carlo is clipped by its deadline and the network is not. So the gain from the network is accuracy (MAE 0.026 vs 0.093 to 0.099, no +5-point bias), not time.
- **Equity is only about 30% of the bot's thinking**, so the cheapest step saves only 27%. The rest is preflop, `on_hand_end` (layer 2's 0.050 s vs v1-fast's 0.033 s) and postflop logic. If the platform ever needs a deeper cut, it has to come from somewhere other than equity.
- **The pace steps mostly guard the first 40% of a round.** With `round_target_s` 5 s and `round_stop_s` 2.5 s, 1.2x pace passes 2.5 s at hand 417 and 1.5x pace at hand 333. After that only `round_stop_s` can fire. I followed the SPEC's 5 s. If own thinking (which excludes transport) should really pace toward 2.5 s, set `round_target_s` to 2.5.
- **With the network on, `round_budget_s` (v1-fast's absolute 1.2 s cut to 10 rollouts) no longer applies**: the pace replaces it, as the SPEC says. If the bot's own perf_counter reads above 1.2 s on the platform, v1-fast cut rollouts for the rest of the round and this bot does not. Its 2.03 s from round r024 may include that cut. Not verifiable here. The first upload's `think_s` will show it.
- **Thresholds were tuned against a Monte Carlo that reads 5 points high.** With an unbiased network, every equity threshold (`value`, `big_value`, `sticky_allin`, `call_margin`) is in effect 5 points tighter. It still wins +10.7 on the real clones. A re-tune with the network on was not done and may gain more.
- **Step 3's 3 rollouts are noisy** (MAE 0.26). An all-win draw reads 1.0 and can trigger a shove. I kept rollouts for every step because they are this bot's only cheaper estimates and v1-fast already uses them past `round_stop_s` (6 rollouts there). Raising `stop_trials` to 6 costs about 5% more thinking in that step (0.524 s vs 0.498 s).
- **The check reads a Monte Carlo bot as cheaper under load.** It counts thread CPU, but the Monte Carlo stops on a 0.6 ms wall-time deadline, so a busy laptop cuts its rollouts and its CPU. The network does its full work whatever the load. Comparing the candidate with layer 2 or v1-fast on a busy laptop therefore favours them. A quiet-laptop run of the check would settle whether the candidate is under 2.04 s.
- Not rebased onto Anh's v1-fast fixes (not mine to do). Nothing pushed, nothing posted.
