# multiway-awareness / minimal

File: `candidates/improved/tournament/multiway-awareness/minimal.py` (current `v0_skeleton/bot.py` + `hook_betting` and `_mw_` helpers/constants only).

## What changed
Only `hook_betting` (postflop, `to_call == 0`), and only when **2 or more opponents are live**. Heads-up it returns `None`, so the incumbent plays as before.
- Win rate vs all live opponents (incumbent `_estimate_win_rate`: random hands, ties count as wins), using up to 64 rollouts within 1.8 ms (the incumbent uses about 32 in 1.2 ms).
- `win_rate > 0.85`: shove (same as the incumbent; stations pay off).
- `win_rate >= thr(n)`: value bet `agent.size(state, ctx, 'value', 0.6)`, a moderate 0.6 pot (it goes through `hook_sizing` if someone replaces that).
  thr(2) = 0.53, thr(3) = 0.46, thr(4+) = 0.42. As a multiple of fair share 1/(n+1), that is 1.59x / 1.84x / 2.1x+, so it rises with the number of opponents.
- Otherwise: check. **No bluffs** with 2+ opponents.
- No tracking and no new trackers.

What the incumbent did here: it bet only at win rate > 0.75 (vs random, about 32 noisy samples), and then either min-raised (0.75–0.85) or shoved. Multiway, a win rate of 0.45–0.75 vs 3–4 opponents is a strong hand, so the incumbent checked through a lot of value against limpers and stations, and its min-bets earned almost nothing.

## Self-test (300 deals, all seats rotated, paired vs incumbent in slot 0; bb/100, 95% CI)

Final file (`minimal.py`), seed 11:

| field | diff ± 95% CI | mean ms | max ms | err/illegal/timeout |
|---|---|---|---|---|
| multiway-awareness | **+64.1 ± 69.7** | 1.11 | 12.4 | 0/0/0 |
| gen_shover | +92.2 ± 94.7 | 1.17 | 12.5 | 0/0/0 |

Identical hook logic (scratch copy on the older skeleton; the skeleton change only touches history replay, which the local arena does not use because `observe` is called):

| field | seed | diff ± 95% CI | mean ms |
|---|---|---|---|
| multiway-awareness | 11 | +81.0 ± 66.6 | 2.11 (workers 2) |
| multiway-awareness | 12 | +111.6 ± 87.2 | 1.88 |
| gen_soft | 11 | +65.4 ± 72.6 | 0.94 |
| gen_tough | 11 | +0.8 ± 62.4 | 0.94 |
| opponent-model | 11 | +21.4 ± 54.1 | 0.95 |
| gen_shover | 11 / 12 | -20.8 ± 88.9 / +46.1 ± 96.6 | 1.75 |

Rejected variants:
- The **same logic also applied heads-up** (thr(1) = 0.62): scenario +53.9 ± 68.4, but gen_shover -61.7 ± 95.9, gen_tough -13.0, opponent-model -6.3. Betting 0.6 pot heads-up at 0.62–0.75 invites raises, which the incumbent's facing-bet logic (call if win rate > 0.5) handles badly. So heads-up was left to the incumbent.
- Value fraction 0.85 instead of 0.6: +2.8 ± 44.5 vs 0.6 on the scenario, so no clear difference. Kept the moderate 0.6.

Note: the incumbent's sampling is deadline-based, so base numbers move between runs even with the same seed (for example, gen_shover base was 66.5, 8.4 and 42.0 in three runs). All CIs are wide. The scenario gain is positive on every run (+54 to +112), while the general fields are mixed but never significantly negative. **Hypothesis until Phase 3.**

## Rationale, when NOT to use, trigger
Hypothesis: against weekend-bot fields, multiway postflop pots are mostly limpers and calling stations that call with any piece of the board, and they rarely bluff-raise. A bot that needs about 75% raw win rate before betting checks back a lot of hands that are well above fair share, and loses value bets that 2–3 callers would pay. Requiring a win rate that is a growing multiple of fair share keeps the bets to hands that are still good against several callers. Never bluffing removes the multiway bluffs, where P(all fold) collapses.

**Do not use when:** the multiway opponents are aggressive check-raisers or maniacs. Thin value bets of 0.6 pot then face raises, and the incumbent's facing-bet logic calls those too loosely. Also do not use when a different `hook_facing_bet` makes the bot fold too much to raises (thin bets turn into bet-folds). This patch does nothing heads-up, so it cannot fix heads-up leaks.

**Trigger condition (live-detectable):** use it when the bot often sees 3+ way flops (for example, more than 30% of the flops it sees have 2+ live opponents), and the opponents in those pots are passive: postflop raise frequency below about 10% of their postflop actions (from `agent.stats` bets_raises/calls) and VPIP above 35%.
