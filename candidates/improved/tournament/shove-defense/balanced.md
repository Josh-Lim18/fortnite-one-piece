# shove-defense / balanced

File: `candidates/improved/tournament/shove-defense/balanced.py` (copy of `v0_skeleton/bot.py`; only `hook_facing_allin` changed, plus private `_sd_*` helpers and constants placed next to it. No tracker. `OpponentStats`, the evaluator, `sanitize`, `S()` and the Agent routing are unchanged.)

## What changed
`hook_facing_allin` (the skeleton calls it when `to_call >= 0.5 * our stack`) is now a **fixed, non-adaptive** rule. It never reads opponent stats.

**Preflop (the main case).**
- Reads `history`, `bets`, `all_in` and `folded` and splits the other live players into:
  - the jammer (the last raiser this street);
  - callers (already matched the bet, or all-in);
  - players behind (have not matched yet). Earlier raisers who still have to act are counted separately.
- Each opponent gets a fixed mixture over four primitive ranges: top 100% / 40% / 15% / 5%, with hands ordered by equity vs one random hand.
  - Open jam (no raise before it): 0.75 / 0.08 / 0.08 / 0.09.
  - Jam or stack-sized raise over an earlier raise: 0.50 / 0.10 / 0.17 / 0.23.
  - Callers and overcallers: 0.25 / 0.35 / 0.22 / 0.18.
- Equities come from an embedded table (18 KB literal). A standalone C Monte Carlo produced it offline, at 6000 samples per entry. It holds the equity of each of the 169 hand classes vs every multiset of 1–3 primitive opponents. Equity is linear in each opponent's hand distribution, so equity vs the mixtures is an exact weighted sum of table entries. For 4+ opponents it extrapolates as eq3·(eq3/eq2)^(n−3).
- Overcalls: each player behind overcalls with probability 0.11 (0.30 for an earlier raiser still to act), capped at 2 overcallers. EV(call) is averaged over 0, 1 or 2 overcalls, each with its own larger pot and lower equity.
- Calls iff EV(call) > 0. If a re-raise is legal (a stack-sized raise that is not all-in) and our equity vs the committed players is ≥ 62%, it jams instead.
- Implied ranges:

  | Spot | Calls about |
  |---|---|
  | BB vs open jam, no one behind | 34% of hands |
  | BTN vs jam, blinds behind | 23% |
  | Early seat vs UTG jam, 6 behind | 19% |
  | BTN vs jam plus one caller | 12% (77+, AJo+, KQo, suited broadways) |

  Decision time is under 0.1 ms.

**Postflop (rare: about 18 spots per 4,000 hands in gen_tough).**
- Monte Carlo with the skeleton evaluator against the jammer plus the callers.
  - Jammer's hand: random with p = 0.30, otherwise a "made hand". A made hand is two pair or better using a hole card, a pair using a hole card at or above the 2nd board rank, or a flush draw.
  - Callers' hands: random with p = 0.10.
- Calls if equity ≥ pot odds + 0.03 per player behind (+0.06 per raiser behind). Jams if equity ≥ 0.70 and a raise is legal.
- Budget: 7 ms (at least 30 samples). It uses a **private RNG**, so it does not consume `agent.rng`, which the default policy depends on.

## Self-test (arena.compare, cand vs incumbent in slot 0, `--workers 1`)
Seed 11, 300 deals × 8 rotations:

| field | diff bb/100 ± 95% CI | cand | base | err/ill/t-o | mean ms | max ms |
|---|---|---|---|---|---|---|
| shove-defense | **+95.9 ± 126.7** | 140.4 | 44.5 | 0/0/0 | 1.75 | 21.6 |
| gen_soft | +46.4 ± 109.4 | 89.9 | 43.4 | 0/0/0 | 1.85 | 24.4 |
| gen_shover | +48.5 ± 106.5 | 111.5 | 63.0 | 0/0/0 | 1.43 | 20.1 |
| gen_tough | +51.4 ± 48.7 | 30.7 | −20.7 | 0/0/0 | 1.73 | 27.2 |
| opponent-model | **+333.6 ± 168.9** | 381.4 | 47.7 | 0/0/0 | 0.84 | 20.9 |

Confirmation run, seed 7, 400 deals:

| field | diff ± 95% | mean ms | max ms |
|---|---|---|---|
| shove-defense | +85.6 ± 109.3 | 1.84 | 28.1 |
| gen_tough | +15.6 ± 46.3 | 1.64 | 20.1 |
| gen_soft | +97.3 ± 97.1 | 1.60 | 20.2 |

The paired CIs are wide for two reasons: the incumbent's MC is time-capped, so its decisions are not deterministic, and opponent models drift. Per field, only opponent-model and gen_tough (seed 11) clear zero. Every point estimate is positive, and no field is negative.

**Lower-variance offline check (hypothesis support).**
- I logged every preflop facing-all-in spot the candidate met: 4,674 spots across the 5 fields, seed 41, 400 deals. For each, I computed the true equity vs the committed opponents' actual hole cards (300-board MC).
- Summed EV(call − fold) of the decisions, in bb, under two models of the players behind: (A) none of them overcall; (B) each one holding a top-15% hand overcalls.

  | Policy | A | B |
  |---|---|---|
  | incumbent | 11.2k | 11.6k |
  | this candidate | 34.4k | 21.8k |
  | earlier, tighter weights (0.62 random) | 26.6k | 19.7k |

- That works out to roughly +65 to +145 bb/100 over these fields from the preflop rule alone.
- A diagnostic on the 18 postflop spots in gen_tough found the postflop rule better than the incumbent's default on the hands where the two disagreed.

## Rationale, when NOT to use, trigger
Rationale (hypothesis): a frequent jammer produces many more jams than a selective one. So, given that we face a jam and know nothing about who made it, the jam is most likely near-random. Weighting the assumed jam range about 75% random (open jams) is therefore close to the frequency-weighted truth for a field that contains any always-all-in or timer shover. The 25% tight weight, the much tighter models for callers, and the overcall shading for every player behind cap the loss when the jammer is actually selective. No per-opponent state means nothing to learn, mis-learn, or be fooled by: no timer trap, and no deceptive history. It also behaves identically from hand 1, which suits short matches.

**Do NOT use** in a field where jams come mostly from selective bots (chart bots that jam only QQ+/AK, or 4-bet-jam-only bots) and no always-all-in or timer shover is present. There the rule calls hands like A5o, K9s and 33 against a range they cannot beat, at roughly −40bb per call. The exploitative or adaptive solver, which reads per-seat shove frequency and showdowns, should then be preferred. It is also not tuned for unequal-stack tournaments or ICM: it is pure chip EV and assumes reset stacks.

**Trigger condition** (detectable live): at least one opponent has shove_pf / hands ≥ 0.10 over 30+ hands, or any jammer has shown a hand outside the top 40% at showdown. In other words, preflop all-ins are frequent at the table. This solution is most useful early in a match or in short matches, before an adaptive per-seat jam model has enough samples, and as the fallback inside an adaptive bot when a seat's sample is small.
