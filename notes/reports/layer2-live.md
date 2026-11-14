# Layer 2 in v1-fast: report

Branch `layer2/live`. Commits: `6ed65af` (full model with personalities), then `dfcebaf` (final).

**Contract change (for Anh):** `_rate` now multiplies `k` by `self.w`, because counts are hand-weighted floats that fade with a 150-hand half-life. Only pass Seat counts to it. `_seat` returns a `Track` (a Seat subclass). `pfr` and `shove` are rebuilt every hand from `pfr_own`/`shove_own`, so layer 1 must not write them. Every call site keeps its name and meaning, and with the layer switched off the bot plays chip-for-chip like v1-fast on 6 seeds.

**Final bot:** counts that fade, plus the cheap random-or-strategic read (raises that show no stronger hands than calls widen pfr and shove toward vpip). I cut personalities. Against the real clones, more personality weight did worse (type_w 0/3/6/12: −0.1/−1.4/−1.6/−7.3, ±3, 128 rounds), mostly through the shove-call read. It gained nothing on any pool and was the costliest part.

bb/100 vs v1-fast, paired:

| Pool | with personalities | final |
|---|---|---|
| kit/examples, 32 rounds | +159.2 ± 34.7 | **+189.9 ± 35.3** |
| kit/bot.py, 32 rounds | +2.0 ± 6.4 | +7.3 ± 5.9 |
| opponents/*.py, 32 rounds | −7.4 ± 8.2 | +1.4 ± 7.1 |
| opponents/real (main), 32 rounds | −11.9 ± 6.3 | +6.7 ± 6.3 |
| opponents/real, 128 rounds, seed 2 | −1.6 ± 2.9 | +0.9 ± 2.6 |

**check_submission:** size 44,159 B, imports, Agent and 3.12 load all PASS. All 4 formats PASS with 0 errors (no_limit timeouts 0–0.78%). Own thinking FAILS at 0.60–0.62 s against the 0.40 s limit. Run back to back at load average 28–45, v1-fast also fails, at 0.48–0.60 s.

**Thinking ratio vs v1-fast:** 1.08 (8 real rounds), 1.03–1.27 in the check pairs. **Layer 2's own cost:** `on_hand_end` takes 0.040 s per round in the check (v1-fast: 0.019–0.026). A microbenchmark puts it at about 3 µs a hand more than v1-fast. Reads add one multiply per `_rate` call.

**fitted.py:** main `c816533` (k=5, real plus simulated), used in `6ed65af`. The final bot uses none.

**Verdict: upload.** It wins kit/examples by more than 5 SE and loses nowhere beyond the error bars. It is neutral on the real clones, and the gain comes from widening against random raisers.
