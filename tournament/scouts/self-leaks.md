# Scout report: OUR OWN LEAKS (self-leaks)

Scout angle: leaks in the assumed incumbent baseline that weekend opponents could see or exploit, plus leaks that cost EV whatever the opponents do.

**Assumed baseline:** we have not seen the incumbent code yet; this is the brief's description.
- Preflop: open, 3-bet and call charts by position.
- Postflop: Monte-Carlo (MC) equity against random or estimated ranges, compared with pot odds.
- Bet size set by hand strength, with no balancing: strong = 3/4 pot, medium = 1/2 pot, bluff = 1/3 pot.
- Raise amounts are raise-to totals.

**Status:** every claim below is a hypothesis until it passes the arena. The bb/100 numbers are rough estimates worked out by hand, not simulations. Format: 100 bb stacks, blinds 10/20, 7–8 players per table, stacks reset every hand.

Reference math used throughout:
- Correct bluff share of a polar range at bet size s (as a fraction of pot): `s / (1 + 2s)`. That gives 1/3 pot → 20%, 1/2 → 25%, 3/4 → 30%, pot → 33%, 2x → 40%.
- Minimum defence frequency (how often the defender must continue so bluffs don't auto-profit): `1 - s/(1+s)`. That gives 1/3 → 75%, 1/2 → 67%, 3/4 → 57%.
- Break-even calling equity: `call / (pot_after_call)`.

## Ranking (impact x likelihood)

| # | id | est. impact (bb/100) | likelihood |
|---|----|----------------------|------------|
| 1 | `static-shove-response` | 20–80 when a maniac sits at the table; ~0 otherwise | high |
| 2 | `multiway-equity-vs-random` | 5–15 | high |
| 3 | `raise-range-blindness` (overcalling raises, reverse implied odds) | 3–10 | high |
| 4 | `size-strength-tell` (unbalanced sizes, no per-opponent sizing) | 3–10 | med |
| 5 | `no-realization-or-position` (single-street pot odds) | 3–8 | med-high |
| 6 | `deterministic-capped-lines` (check means give up, no mixing) | 2–6 | med |
| 7 | `action-construction-and-latency` (raise-to maths, SPR, MC timeouts) | 0–20 (tail risk) | low-med |

---

## 1. `static-shove-response`

**Description (hypothesis).** The preflop call charts are built for a normal opponent: call a 3-bet or 4-bet or a shove with roughly QQ+/AK (about 2.6% of hands). CONTEXT.md expects always-all-in bots and bots that shove at random. Against them, a static chart folds far too often. The baseline probably has no per-opponent read of how often each opponent goes all-in.

**Why it costs bb/100.**
- An always-all-in bot's range is close to random. Calling a 100 bb shove as a non-blind seat:
  - Pot after calling: 1.5 + 100 + 100 = 201.5 bb, so break-even equity is 100 / 201.5 ≈ 49.6%.
  - About the top half of hands has ≥50% equity against a random hand.
  - Tightening for players still to act (they can overcall or wake up) gives a calling range of roughly the top 20–30%.
- Average equity of the top 25% against a random hand is about 60–62%. EV per call ≈ 0.61 × 201.5 − 100 ≈ +23 bb.
- The chart takes about 2.6% of these spots. The fix takes about 25%, so roughly 22% of the time we fold a call worth +20 bb.
- Other bots compete to pick the maniac off. Suppose we are the first caller in about 1/6 of the maniac's shoves and the maniac shoves almost every hand: 100 × (1/6) × 0.22 × 23 ≈ 85 bb/100. Discount this for multiway overcalls and maniacs that only shove sometimes: **20–80 bb/100 at tables with ≥1 maniac**.
- This is likely the largest single item if the field really contains shovers.

**Reproducible test.**
```
bot Maniac:      act(): if 'raise' in legal: raise to max_raise_to else call
bot RandomShove: act(): with p=0.3 shove; else play a tight-passive chart
table mixes:
  A) incumbent + 1 Maniac + 5 TightPassive              (single maniac)
  B) incumbent + 1 Maniac + 2 CallingStation + 3 TightPassive
     (competition to pick the maniac off; tests multiway all-in thresholds)
  C) incumbent + 2 RandomShove + 4 mixed                (partial shovers)
measure:
  - incumbent bb/100 in A/B/C vs a candidate that calls with equity_vs_range(shover_range) > needed
  - self-model: per opponent, logged shove frequency vs incumbent call frequency
    facing that opponent's shove; flag if call_freq < 10% while opp_shove_freq > 50%
duplicate deals + seat rotation, >= 20k hands per mix
```

**Fix ideas.**
1. Per-opponent counters for all-ins (VPIP, PFR, all-in frequency) with a Bayesian prior. Facing an all-in, build the opponent's range as the top-k% of hands, where k comes from their observed shove frequency. Call when `equity(hand, range, n_live_callers) > call / pot_after_call + margin`, with the margin growing for each player still to act.
2. Precompute a lookup table: shove-range width × number of players still to act × our hand class → call or fold. This keeps the decision under 1 ms.

---

## 2. `multiway-equity-vs-random`

**Description (hypothesis).** The postflop MC is run against one random hand, or against n random hands, and then compared with pot odds. Both versions overstate our equity in multiway pots:
- Against one random hand when there are 2–4 opponents: a large error.
- Against n random hands: the players who saw the flop and kept calling are not random; their ranges are stronger.

**Why it costs bb/100.** Rough numbers: top pair with a weak kicker (A5 on A-9-4 rainbow) has about 85% equity against one random hand and about 60% against three random hands. Against three ranges that called a raise and then a flop bet, it may be only 30–40%.
- The baseline would build a pot with a hand that is behind its true opposition. It would also call too wide with non-nut draws, for example a low flush draw or a straight draw that makes a flush possible.
- A 7–8-handed field full of calling stations makes multiway pots common. If about 10% of our hands reach a multiway flop and we overcommit about 5 bb per such hand: **5–15 bb/100**.

**Reproducible test.**
```
self-model calibration (harness has oracle access to all hole cards):
  for each incumbent postflop decision:
     E_est  = equity the incumbent used
     E_true = exact equity vs actual live opponents' hole cards (enumerate remaining board)
  report mean(E_est - E_true) and a calibration curve, bucketed by n_live_opponents in {1,2,3,4+}
  red flag: bias > +0.10 at n >= 3

exploiter table "StationNit":
  bot Station: call any bet with pair+ or 8+ outs; never raise
  bot NitRaiser: postflop raise only with two-pair+; else check/fold
  mix: incumbent + 3 Station + 2 NitRaiser + 1 TightPassive
  compare incumbent bb/100 vs candidate with range-weighted multiway equity
```

**Fix ideas.**
1. Run the MC against n = live opponents, not 1. Sample each opponent's hand from a range that has been narrowed by their actions: preflop VPIP/PFR band → flop call (drop the bottom x%) → raise (keep the top y%).
2. Add a multiway penalty: needed equity = pot odds + δ(n, players still to act behind). Allow stacking off only with hands whose equity is high against the narrowed ranges, not against random hands.

---

## 3. `raise-range-blindness` (overcalling raises, reverse implied odds)

**Description (hypothesis).** When facing a raise, the baseline still estimates equity against a random or generic range. A raise from a tight-passive bot almost always means a strong hand, yet "top pair = 80% against random" leads to calling. Each call commits us to the next street with a hand that wins little when ahead and loses a lot when behind. That is reverse implied odds: dominated aces, weak kickers, non-nut flushes, the low end of a straight. The same blindness preflop means flatting 3-bets with KJo, AJo or KQo out of position.

**Why it costs bb/100.** The rare postflop raise from a passive or nit bot is the nuts or close to it. Stacking off with one pair costs about 50–100 bb each time. If a nit raises in front of us about once every 150–300 hands and we call down: about 3–7 bb/100. Calling preflop 3-bets with dominated hands adds about 1–3 bb/100. Total **3–10 bb/100**. Against maniacs the leak goes the other way, folding too often (see #1). The root cause of both is that the response to aggression is not tied to the opponent.

**Reproducible test.**
```
bot NutRaiser (tight-passive):
  preflop: call with top 30%, raise only QQ+/AK
  postflop: call with pair+, raise ONLY with sets+/nut flush/straight, never bluff
mix: incumbent + 2 NutRaiser + 4 CallingStation
measure:
  - incumbent showdown win% when calling a postflop raise (target: >= break-even equity)
  - chips lost in hands where incumbent called a raise with one pair
  - reverse-implied-odds probe: frequency of incumbent calling flop with A-weak/K-weak top pair
    then losing > 30bb at showdown to a better kicker
```

**Fix ideas.**
1. Treat each opponent's postflop raise frequency as a narrowing signal: their raise range = the top r% of hands, where r is their observed raise frequency (prior r = 5%). Recompute equity against that range before calling.
2. When committing a large share of the stack, apply a domination discount: in raised pots, subtract a fixed equity margin for hands that can be dominated (weak kicker, non-nut draw).

---

## 4. `size-strength-tell` (unbalanced sizes, no per-opponent sizing)

**Description (hypothesis).** Bet size maps directly to hand strength, so the size reveals the hand:
- Every 1/3-pot bet is a bluff or weak, against a correct bluff share of 20%.
- Every 3/4-pot bet is strong, against a correct bluff share of 30%.
- 1/2-pot bets are medium hands, which fold to a raise.

**Why it costs bb/100.**
- **Against an opponent who reads sizes**, for example an adaptive bot after about 30 samples:
  - Raising every 1/3 bet wins pot + bet, roughly 1.33P each time. Our bluffs fold, and our medium hands fold too.
  - Folding everything but the nuts to 3/4 bets wipes out our value, about 0.4 × 0.75P per value bet.
  - If river and turn bets happen in about 3% of hands, each side costs about 5–10 bb/100 at a 10 bb average pot. Only 1–3 of 7 opponents adapt, so the realised cost is about **2–6 bb/100**.
- **Against opponents who do not adapt**, the fixed sizes lose EV in any case:
  - Calling stations: bet bigger for value, about 3/4 to pot, and never bluff. Our 1/3 bluffs are called every time.
  - Nits: bluff more, and smaller works.
  - Fixed sizes leave about **1–4 bb/100** on the table.

**Reproducible test.**
```
self-model measurement (no exploiter needed):
  log (street, spot, size_bucket, hand_strength_pct vs our own range in that spot)
  report Spearman corr(size, strength) per street; per bucket bluff share
     bluff := equity vs opponent continue range < 0.3
  pass: |corr| < 0.2 on river; bluff share per bucket within ±0.1 of s/(1+2s)
     (or a documented exploit choice per opponent class)

bot SizeReader (cheat-knowledge, fixed exploit; for test only):
  vs incumbent bet <= 0.4 pot:  raise to 3x with any two cards
  vs 0.4 < bet <= 0.6:          raise with pair+, else fold
  vs bet >= 0.7 pot:            fold unless two-pair+
bot AdaptiveSizeReader: learns the bucket→showdown-strength map online and applies the
  rules above once n >= 30 per bucket (checks that the leak can be learned in tournament time)
mixes: heads-up incumbent vs SizeReader; incumbent + 1 AdaptiveSizeReader + 5 fillers
compare to the same mix with SizeReader replaced by a neutral TAG bot
```

**Fix ideas.**
1. Pick the size from the spot (board texture, SPR, opponent class), not from hand strength. Fill each size with value and bluffs at about `s/(1+2s)` bluff share. Use a seeded RNG to mix hands that sit near a threshold.
2. Override per opponent class: against stations (low fold-to-bet), bluff share = 0 and value size 3/4 to pot; against nits (high fold-to-bet), raise the bluff share. The table can't exploit this, because the stations never adapt.

---

## 5. `no-realization-or-position` (single-street pot odds, position ignored postflop)

**Description (hypothesis).**
- **Draws.** MC equity runs to the river and assumes we see every remaining card for free. Comparing it with this street's pot odds overvalues draws and weak hands that face more bets later. Out of position, equity realisation is often about 0.7–0.85; in position it is about 1.0–1.1.
- **Position.** Postflop thresholds are the same in position and out of position. Preflop charts by position cover only part of the effect.

**Why it costs bb/100.** Example: a flop call with 30% raw equity at pot odds of 25% looks profitable. Against a bot that keeps betting, that equity is not realised: we fold the turn when we miss, and we get paid less when we hit. That costs about 0.5–1 bb per such call. At 5–8% of hands, the total is **3–8 bb/100**. The out-of-position part grows against aggressive bots that bet every street.

**Reproducible test.**
```
bot Barreler: bet 3/4 pot every street when checked to or first to act; call raises with top 40%
mix: heads-up incumbent vs Barreler (both positions), and incumbent + 2 Barreler + 4 TightPassive
measure:
  - EV of incumbent flop calls bucketed by raw MC equity (20-30%, 30-40%, ...)
    and by position (IP vs OOP); negative EV buckets that pot-odds said were +EV = leak
  - incumbent bb/100 in single-raised pots IP vs OOP vs a realization-adjusted candidate
```

**Fix ideas.**
1. Required equity = pot odds / R, where R is a realisation factor indexed by (in or out of position, street, hand class such as draw / made / air, SPR). Fit R from arena logs.
2. Add implied-odds and reverse-implied-odds terms when there are two streets left. Price a draw by its nut-hit equity × expected future pay-off from that opponent, not by raw river equity.

---

## 6. `deterministic-capped-lines` (check = give up, no mixing)

**Description (hypothesis).** Pure thresholds give a pure strategy:
- Every hand that bets does so with the same size.
- A check means a weak hand, because the baseline has no check-raise and no slowplay. So a check reliably signals a capped range that will fold to a bet.
- The same hand in the same spot always gets the same action.

Many simple rule bots bet when checked to. They exploit this by accident, and a bot that models opponents exploits it on purpose.

**Why it costs bb/100.** If we fold more than 33% after checking, a half-pot stab profits on fold equity alone. A capped checking range probably folds 50–60% of the time. Being stabbed in about 5% of hands, at 2–3 bb lost each, costs about 1–2 bb/100 against bots that bet when checked to. An adaptive opponent who stabs, floats, and folds to our big sizes also adds about 1–4 bb/100. Total **2–6 bb/100**.

**Reproducible test.**
```
bot Stabber: heads-up, whenever incumbent checks to it -> bet 1/2 pot with any hand; fold to raise
bot Floater: call incumbent c-bet IP with any two cards, bet turn if incumbent checks
mix: incumbent + 1 Stabber + 1 Floater + 4 TightPassive; also heads-up vs each
measure (self-model):
  - fold-to-bet% after incumbent checks (flag > 45% vs 1/2 pot)
  - check-raise frequency (flag ≈ 0%)
  - action entropy given (hand bucket, spot) — flag ≈ 0 bits in river/turn spots
  - Stabber net vs incumbent (should be <= 0 if fixed)
```

**Fix ideas.**
1. Protect the checking range: with a seeded RNG, check a share of strong hands, and add check-raises with strong hands plus some draws. Set the share so the checking range folds at most about `1 - MDF(0.5)` ≈ 33%.
2. Per-opponent rule: if an opponent's bet-when-checked-to frequency is above 60%, check-call wider and check-raise more against them.

---

## 7. `action-construction-and-latency` (raise-to maths, SPR, MC timeouts)

**Description (hypothesis).** Errors in building the action that cost EV whatever the opponents do:
- **Raise-to vs raise-by.** Computing a "3/4-pot raise" as `0.75*pot` without adding the current bet and the amount to call gives a raise-to below `min_raise_to`. It then gets clamped to a min-raise, a weak raise with our value hands, or fails as an illegal action.
- **No SPR rules.** When the stack left after a bet is under about 1/3 pot, the right play is usually an all-in. Without that rule the baseline leaves awkward small amounts behind, or folds after committing most of its stack.
- **MC latency.** The MC iteration count scales with the number of opponents. In 7-way spots it can exceed the ~50 ms budget, and the engine then folds or checks for us, even with strong hands.
- **Edge cases.** `to_call >= stack`, `min_raise_to > max_raise_to`, a missing `'raise'` in `legal`, or side pots.

**Why it costs bb/100.** Usually close to 0. Large when it triggers: one timed-out fold of a 50 bb pot every 500 hands costs 10 bb/100. Min-clicked value raises cost about 1–3 bb/100. **Tail risk 0–20 bb/100.**

**Reproducible test.**
```
fuzz harness (no opponents needed):
  generate 100k random legal obs incl. edge cases:
     n_live in 2..8, stacks in [1, 2000], to_call in {0, < stack, == stack, > stack},
     min_raise_to == max_raise_to, legal without 'raise', multi-way all-in side pots
  assert: action in obs.legal; if raise: min_raise_to <= amount <= max_raise_to; no exceptions
  assert: p99 act() latency < 40 ms, max < 50 ms, measured with 7 live opponents
  semantic check: for every raise, intended_fraction = (amount - max(bets)) / (pot + to_call)
     compare to the size the strategy requested; flag deviations > 10%
  SPR check: log raises leaving 0 < behind < 0.33*pot -> should be all-in instead
```

**Fix ideas.**
1. One helper is the only place that builds a raise:
   `raise_to = max(bets) + f * (pot + to_call)` (the sizing formula). Clamp the result to `[min_raise_to, max_raise_to]`, then snap to all-in if `stack_behind_after < 0.33 * pot_after`.
2. A time-budgeted MC: stop at a deadline (for example 30 ms) rather than at a fixed iteration count. Precompute preflop and common-case equity tables, and wrap `act()` in try/except so it falls back to check or fold when the action is legal.

---

## Cross-cutting note

Leaks #1, #3 and #6 share one root cause: the response to aggression and passivity does not depend on the opponent. A small per-seat stats module (VPIP, PFR, aggression factor, fold-to-bet, all-in rate, bet-when-checked-to) with priors would feed all three fixes. It would likely be the highest-leverage single change against a field of weekend bots (hypothesis).
