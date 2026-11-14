# Tournament results

## Against the live bot (authoritative for upload decisions)
Team simulator `tools/sim.py` on `poker/live` (official kit engine), paired seeds, default pool, 160 rounds x 1,000 hands:
autopicker-lc vs v1-fast **-37.6 ± 10.0 bb/100**; autopicker-lc-baseline vs v1-fast -58.9 ± 11.1;
layers 2-4 on vs off **+16.5 ± 5.5**. So autopicker-lc is research, not an upload candidate; the auto-picker layers are
the part worth porting onto v1-fast.

## Tournament-day numbers (local dependency-free kit-mode arena, not included in the repo)

Format: 2,000 chips, 10/20, kit `state`, `on_hand_end`, 10 ms limit -> check/fold. Duplicate deals, full seat rotation,
paired vs the incumbent (`candidates/incumbent/bot.py`, VIVelev Monte Carlo) on identical deals. bb/100 ± 95% CI.

## Plug-ins (Phase 3, 400 deals x 8 seatings)
| candidate | shove-defense | multiway | preflop | gen_soft | gen_shover | gen_tough |
|---|---|---|---|---|---|---|
| preflop-structure/minimal | +206 ± 131 | +458 ± 120 | +69 ± 48 | +270 ± 118 | +207 ± 123 | +102 ± 63 |
| shove-defense/balanced (winner) | +87 ± 104 | +2 ± 25 | -10 ± 17 | +156 ± 106 | +4 ± 92 | -1 ± 30 |
| shove-defense/minimal (backup) | +147 ± 114 | -2 ± 18 | -20 ± 22 | +147 ± 119 | -21 ± 88 | -11 ± 29 |
| multiway-awareness/minimal | +6 ± 26 | +21 ± 36 | -0 ± 28 | +22 ± 52 | 0 ± 12 | +16 ± 35 |
All: 0 errors / illegal / timeouts (fuzz table included).

## autopicker-lc vs incumbent (500 deals x seatings, seed 31337)
| field | autopicker-lc | autopicker-lc-baseline (layer 1) |
|---|---|---|
| amb_mix (ambiguous bots) | **+577 ± 119** | +510 ± 114 |
| amb_image (image players) | **+504 ± 102** | +474 ± 100 |
| amb_cycler (personality cyclers) | **+261 ± 101** | +264 ± 103 |
| shove-defense | **+320 ± 137** | +304 ± 141 |
| multiway-awareness | **+833 ± 140** | +829 ± 137 |
| preflop-structure | **+101 ± 64** | +129 ± 66 |
| gen_soft | **+278 ± 116** | +333 ± 130 |
| gen_shover | **+343 ± 136** | +340 ± 138 |
| gen_tough | **+81 ± 62** | +65 ± 64 |
| opponent-model | **+453 ± 148** | +453 ± 148 |
Robustness (fuzz / heads-up / 7-handed): 0 errors, 0 illegal, 0 timeouts; max decision 6.1 ms, mean 0.1–0.6 ms.

## Do layers 2–4 add value? (paired on identical deals, 600 deals, seed 777)
| comparison | amb_image | amb_cycler | amb_mix | gen_soft | gen_shover | gen_tough |
|---|---|---|---|---|---|---|
| full − baseline | +42 ± 69 | +37 ± 57 | +64 ± 75 | -70 ± 105 | -9 ± 18 | -23 ± 27 |
| picker on − off | -10 ± 56 | -2 ± 56 | +15 ± 76 | -31 ± 92 | 0 ± 0 | +11 ± 28 |

**Honest read:** almost all of v1's gain over the incumbent comes from layer 1. Layers 2–4 lean positive against
ambiguous/deviating bots and slightly negative in soft fields, but nothing is significant at this sample size, and the
picker states add ~0 on top of personalities so far. The picker does detect style switches (vs the cycler it flagged
each switch within 5–14 hands and relearned within ~40). Next: tune knobs on gen_soft (suspect: bluffing labelled
folders on thin data, value_mult vs maniacs), then confirm in Josh's arena with `--until-decided`.
Both builds are registered in `arena/bots.toml` (`autopicker-lc`, `autopicker-lc-baseline`). Note: these local runs used larger
thinking budgets than the current build, and their layer comparison was not significant; the team-simulator runs above supersede them.
