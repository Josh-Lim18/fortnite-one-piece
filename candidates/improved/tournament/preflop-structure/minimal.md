# preflop-structure / minimal

File: `candidates/improved/tournament/preflop-structure/minimal.py` (copy of `v0_skeleton/bot.py`; only `hook_preflop` plus `_pf_*` helpers changed).

## What changed
The incumbent decides preflop with a 32-sample win rate against ALL remaining opponents (players yet to act count as live). At an 8-handed table that means even AA is below the 0.5 calling bar, so it folds almost everything and min-raises or shoves the rest. The patch replaces that with:

- **Equity table:** `_PF_EQ_STR` holds the heads-up equity vs one random hand for all 169 hand classes (507 characters, 6000-sample MC with this file's evaluator, about ±0.6%).
- **Unopened or limped pot:** raise if equity ≥ the position threshold: BTN/CO 0.565 (~top 30%), HJ/MP 0.59, UTG/UTG+1 0.61, SB/BB 0.575. Add +0.01 per limper. Size is 3bb + 1bb per limper (+1bb from the blinds). Over-limp with pairs or equity ≥ 0.54 behind limpers. SB completes with ≥ 0.52. Otherwise check or fold.
- **Facing one raise:** 3-bet with AKs/AKo/AQs/AJs or 88+, sized 3×raise + 1×raise per caller; if that is ≥ 40% of the stack, shove instead. Call a min-raise for ≤ 1bb more with ≥ 0.45. Otherwise call if equity ≥ 0.585/0.61/0.635 (price ≤ 3bb / ≤ 6bb / more) and the call is ≤ 12% of the stack. Set-mine any pair for ≤ 6% of the stack.
- **Facing a 3-bet or more:** shove QQ+ and AKs. Call TT/JJ, AKo and AQs if the call is ≤ 25% of the stack. Fold the rest.
- **Defers (returns None) when** facing a (near) all-in (to_call ≥ 50% of the stack, which belongs to `hook_facing_allin`), or when `bets`/`stacks` are missing.
- No opponent tracking, no extra trackers.

## Self-test (300 deals × 8 seat rotations, `--workers 1`, base = incumbent)

| field | cand bb/100 | base bb/100 | diff ± 95% CI | err / ill / t/o | mean ms | max ms |
|---|---|---|---|---|---|---|
| preflop-structure (seed 11) | 10.0 ± 48.9 | -4.1 ± 20.6 | **+14.1 ± 52.5** | 0/0/0 | 0.66 | 28.3 |
| preflop-structure (seed 23) | 42.1 ± 59.9 | -1.8 ± 26.8 | **+44.0 ± 63.0** | 0/0/0 | 0.41 | 16.2 |
| preflop-structure (seed 11, after rebase on updated skeleton) | 42.0 ± 55.6 | -1.0 ± 18.7 | **+43.0 ± 56.1** | 0/0/0 | 0.28 | 12.1 |

Note: during the work the shared `v0_skeleton/bot.py` gained a "kit event layer" (`on_hand_end`, history replay). The final file is the *current* skeleton with only the `hook_preflop` block replaced; the last row is from that final file. The other rows were run on the same hook over the earlier skeleton.
| gen_soft | 232.7 ± 115.7 | 42.4 ± 54.0 | **+190.3 ± 114.6** | 0/0/0 | 0.72 | 20.6 |
| gen_shover | 249.6 ± 136.3 | 20.6 ± 89.1 | **+229.0 ± 131.3** | 0/0/0 | 0.65 | 17.9 |
| gen_tough | 46.5 ± 67.1 | 16.7 ± 46.6 | +29.8 ± 76.4 | 0/0/0 | 0.43 | 20.5 |
| opponent-model | 32.2 ± 52.4 | -30.6 ± 41.1 | **+62.8 ± 62.2** | 0/0/0 | 1.82 | 25.1 |

The scenario is positive on all three runs (pooled roughly +34 ± 33), but no single run is significant. gen_soft, gen_shover and opponent-model are significantly positive. Nothing is negative. The max-ms spikes come from machine load (CPUs shared with about 14 agents); the hook itself is a dict lookup.

## Rationale, when NOT to use, trigger
Hypothesis: most of the gain is simply that the bot now enters pots with a sensible top 15–30% range and position, instead of folding nearly every hand and bleeding blinds. The value 3-bets and the iso sizing against limpers add more, because limpers and stations call raises with worse hands. This is a static chart. It ignores who the limpers and raisers are, it values offsuit weak aces and kings by heads-up equity (which overrates them in multiway pots), and it hands postflop play to the unchanged incumbent (which bets tiny or shoves). **Do not use it** if a stronger preflop module (a balanced or exploitative variant with opponent-aware ranges, squeeze and iso adjustments) passes Phase 3, because this is the fallback baseline. Also avoid it at tables full of very aggressive 3-bettors or re-raisers: the fixed calls of opens for up to 12% of the stack and the folds to 3-bets can be exploited by a bot that 3-bets light every time. **Trigger condition:** always-on as the default preflop layer whenever no opponent model is warmed up (for example fewer than about 30 hands observed per seat). It is most useful when the table is passive and limp-heavy (average VPIP − PFR above about 25% across seats), where the iso sizing and value 3-bets pay most.
