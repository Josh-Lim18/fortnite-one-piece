# shove-defense / minimal

File: `candidates/improved/tournament/shove-defense/minimal.py`. It is a copy of `v0_skeleton/bot.py` with only `hook_facing_allin` changed, plus `_sd_` helpers and constants placed next to it. It adds no trackers and keeps no state between hands.

## What changed
**Preflop only.** When the skeleton detects a jam (`to_call >= 0.5 * stack`), the hook classifies the other live seats from `bets`. A seat whose bet is at least 0.9 × the top bet is "in the pot" (the jammer and anyone who already called). Any other live seat is "pending". A pending seat with a bet above 1bb counts as an "opener".
- **Nobody has called yet:** call if the hand's equity vs one random hand is at least `0.515 + 0.006*pending + 0.03*openers`. With only the BB left to act that is about the top 40% of hands. With 6 players still to act it is about the top 30%.
- **One caller already in:** call only with 99+, AK, AQ, AJs.
- **Two or more callers:** call only with TT+, AK.
- **Premiums:** with AA/KK/QQ/AKs, raise to max if raising is legal and players are still pending. Otherwise call.
- **Postflop:** the hook returns `None`, so the incumbent plays exactly as before.

The equity table `_SD_EQ1` comes from an offline MC run (169 classes, 6000 deals each, ties split) and is embedded as a literal.

The incumbent's leak (hypothesis, consistent with the results): facing a jam, it rolls out 32 samples vs *every* live opponent, including players who have not acted and will mostly fold, and needs a win rate above 0.5. So it folds nearly everything to an early jam, and then plays far too loose heads-up because ties count as wins and it has no pot-odds or caller-range adjustment.

## Self-test (paired diff vs incumbent in slot 0, `--workers 1`)
Final file, which was rebuilt on the current skeleton (with the kit event layer):
| field | deals | diff ± 95% CI (bb/100) | cand bb/100 | mean ms | max ms | err/ill/t-o |
|---|---|---|---|---|---|---|
| shove-defense | 300 (seed 11) | +84.9 ± 132.2 | 110.4 | 1.04 | 12.6 | 0/0/0 |
| shove-defense | 1200 (seed 21) | **+98.2 ± 68.9** | 218.1 | 1.80 | 24.1 | 0/0/0 |
| gen_soft | 300 | +80.1 ± 113.8 | 108.9 | 1.43 | 14.4 | 0/0/0 |
| gen_shover | 300 | +83.0 ± 116.3 | 111.5 | 1.25 | 12.8 | 0/0/0 |
| gen_tough | 300 | -16.9 ± 54.6 | -6.7 | 1.39 | 25.3 | 0/0/0 |
| gen_tough | 1200 (seed 21) | -11.8 ± 25.9 | -2.7 | 1.66 | 28.9 | 0/0/0 |
| opponent-model | 300 | **+549.7 ± 207.8** | 536.0 | 0.29 | 17.3 | 0/0/0 |

The same hook on the earlier skeleton (identical behaviour) scored: shove-defense 1500 deals (seed 21) +148.2 ± 61.9; gen_soft 1200 (seed 5) +81.8 ± 64.7; gen_shover 1200 (seed 5) +97.6 ± 58.3; gen_tough 1200 (seed 5) -0.7 ± 26.0. Kit mode (`kit_mode=True`, shove-defense, 1 rotation, 150 deals): 0 errors, 0 illegal actions, max 8 ms.

gen_tough has no shovers, so the hook rarely fires there. Its small negative is inside the noise; the incumbent's run-to-run timing nondeterminism alone moves the base number by about 10 bb/100.

The max-ms spikes come from the shared CPU. The hook is a dictionary lookup plus one pass over the seats.

Tuning (variant vs this file, shove-defense, 1500 deals, 2 seeds): the heads-up base threshold scored flat from 0.475 to 0.515. Raising it to 0.545 cost -69 ± 44. Widening or tightening the one-caller list changed nothing measurable (-8 ± 22, -1 ± 25). I kept 0.515 because it gives up the least against jammers that are not random.

## Rationale, when NOT to use it, trigger
Rationale (hypothesis until Phase 3): at these tables most preflop jams come from always-all-in or timer bots with roughly random ranges. Heads-up against a random range the call breaks even at about 49.5% equity, so the top 30–40% of hands are clearly profitable calls. Anyone who calls the jam first is *not* random (stations call with about the top 30%, nits and chart bots with the top 5–8%), so the patch falls back to a short premium list when another player is already in. The rule has no memory, so it cannot be fooled by a timer bot looking like a nit in VPIP stats. The same blindness is its weakness. **Do not use it** when the jams come from tight or value-only players, for example a field of nits or chart bots that only jam QQ+/AK, or adaptive bots that jam strong ranges. There it calls with A8o/K7o/QTo-class hands against ranges that crush them. It is also wrong at tables with no shovers, where it adds nothing, and it does nothing about postflop jams. **Trigger condition** (detectable live): some seat has preflop jammed (`OpponentStats.shove_pf`) in at least ~20% of its hands, or showdowns reveal jam hands outside the top 40%. Below that, fall back to the incumbent's or a tracked solution's jam defence.
