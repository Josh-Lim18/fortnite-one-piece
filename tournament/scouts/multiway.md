# Scout report: multiway pots and position

Angle: 7–8 handed, 100bb, stacks reset each hand, field of loose/weak weekend bots (limpers, calling stations, any-two shovers, a few nits).
Every strategy claim below is a **hypothesis** until it passes the arena. I could not inspect the incumbent (no candidate code in the repo yet), so "likelihood" means "how likely a typical rule/equity bot (and probably our incumbent) has this leak". Solvers should confirm each leak against the incumbent first (run the scenario, read the action log).

## Supporting numbers (scratch Monte Carlo, 2–3k samples, about ±1.5%; ranges built from a Chen-score cutoff)

| Spot | Hero equity |
|---|---|
| AKo vs 1 / 2 / 3 random hands | 66% / 49% / 38% |
| AA vs 1 / 4 random hands | 84% / 56% |
| KQo vs 3 random | 35% |
| K7 on Kh8s2d vs 1 / 3 random hands | 85% / 61% |
| A5s / KJo / 76s vs 4 random | 27% / 28% / 19% (fair share is 20%) |
| Pocket pair flops a set or better | 12.0% (about 7.3:1 against) |
| AJo vs any-two shover alone / + caller (top 15%) / + caller (top 8%) | 62% / 33% / 26% |
| KQo, same three spots | 60% / 31% / 24% |
| TT, same three spots | 75% / 41% / 33% |
| 77, same three spots | 66% / 32% / 28% |
| AKo, same three spots | 65% / 42% / 36% |
| AQs, same three spots | 66% / 40% / 33% |

A 3-way 100bb all-in overcall needs about 100 / (100+100+100+1.5) = 33% equity, and more if someone is still to act behind.

---

## Shared dummy-bot library (pseudocode against the contract)

All bots implement `Agent(seat, num_players, rng_seed)`, `act(obs)`, `observe(event)`. Helpers:

```
legal_or(obs, pref):   # first legal action in preference list
    for a in pref: if a in obs.legal: return {'action': a}
    return {'action': 'fold'}
raise_to(obs, x):      return {'action':'raise','amount': clamp(x, obs.min_raise_to, obs.max_raise_to)}
chen(hole) -> float    # Chen formula; >=10 ~ top 6%, >=8 ~ top 15%, >=7 ~ top 20%, >=5 ~ top 40%
made_pair_or_better(hole, board) -> bool
any_draw(hole, board) -> bool   # 4-flush or open-ended/gutshot
```

```
Limper (passive-loose, "weekend preflop"):
  preflop: if to_call == 0: check
           elif to_call <= 1*bb (unraised): call if chen>=2 (about 75% of hands) else fold
           elif to_call <= 4*bb: call if chen>=5 else fold      # calls small raises wide
           else: call if chen>=9 else fold
  postflop: if to_call == 0: check (bets 1/2 pot only with two pair+)
            else call if made_pair_or_better or any_draw or to_call <= pot/4, else fold

Station (calling station):
  never raises. Preflop: call any to_call <= 10*bb; call all-in only with chen>=8.
  Postflop: call any bet if pair, draw, or ace-high; else call 40% at random; never folds a pair.
  (Fold rate to a single c-bet when missed: about 30%; when anything hit: about 0%.)

Shover (always-all-in):
  every decision where 'raise' is legal: raise_to(obs, obs.max_raise_to); else call.

RandomShover (timer/random shover):
  with p=0.25 shove (as above); else play like Limper.

Nit (tight-passive):
  preflop: raise to 3bb with chen>=10, call with chen>=8, else fold/check.
  postflop: bet 2/3 pot with top pair+, call with top pair+, else check/fold.

CallerAfterShove(range_cut):       # the key "overcaller" dummy
  preflop: if someone is all-in: call iff chen >= range_cut   (range_cut = 8 -> top 15%, 10 -> top 8%, 0 -> any two)
           else play like Limper.
```

Hero seat is rotated by `run.py`. Duplicate deals are on. All scenarios run at least 20k hands per seat rotation, unless noted.

---

## 1. `overcall-allin-multiway` (rank 1)

**Description.** Hero faces an all-in that someone else has already called, or with players still to act behind, and uses a calling range tuned for heads-up (for example "call a shove with AJ+, 77+"). Against an any-two shover alone, AJo has 62%. Once a top-15% caller is in, AJo drops to 33%, KQo to 31% and 77 to 32%, all at or below the 33% breakeven. The opposite leak matters as much. If the caller is a station that calls with any two (range_cut=0), AJo has about 47% vs two random hands, so folding gives up about +40bb. The leak is treating "how many are in" and "who is in" as irrelevant.

**Why it costs bb/100 (hypothesis).** One always-shover at the table means a shove on almost every hand. With 7 other players, "shove + one caller before hero" happens in maybe 15–30% of hands. One bad overcall (100bb at 30% equity into about 301bb) loses about 9.5bb. One wrong fold vs two any-two hands with AJo forfeits about 40bb. Misplaying 1–3% of hands this way is about 10–40 bb/100. There is also a second-order effect: players behind can wake up, so with N still to act, the equity needed rises and hero's realised equity falls.

**Reproducible test.**
- Table A ("tight overcaller"): Hero, Shover, CallerAfterShove(range_cut=8), CallerAfterShove(range_cut=8), Limper ×2, Nit ×2.
- Table B ("loose overcaller"): Hero, Shover, CallerAfterShove(range_cut=0), Station ×2, Limper ×3.
- Table C ("players behind"): same as A, but seats are fixed so that Shover is UTG and both CallerAfterShove bots sit *after* hero (hero acts with 2 tight callers behind).
- Metric: hero bb/100 on hands where hero faces a shove; log hero's call frequency by (number already all-in or called, number still to act, hand class). A correct bot calls much tighter in A and C than heads-up and much looser in B. Compare with a reference policy: call iff MC equity vs the per-seat ranges ≥ call / (pot_after_call), with a penalty for players behind.

**Impact / likelihood.** 10–40 bb/100 when a shover is seated (note: with equal reset stacks, any call of a 100bb shove is all-in, so there are no side pots and no postflop play: this is a pure preflop equity-vs-ranges problem); likelihood **high** (equity-vs-random or fixed-chart callers almost always get this wrong in one direction).

**Fix ideas.**
1. Per-seat range model from `observe`: count shoves/calls-of-all-in per seat (VPIP-style counts with a prior: shover = any two once it has shoved ≥5 times in ≥10 hands; caller-of-all-in range = top x%, where x comes from showdowns or defaults to 15%). On each decision, Monte Carlo hero vs *each* live opponent's range (50–100 ms budget → about 300–500 samples with a fast evaluator, or a precomputed lookup table keyed by (hand class, number of opponents, range bucket)). Call iff equity ≥ to_call / (pot + to_call) + margin(players_behind × 3–5%).
2. Cheap patch: a lookup table of call thresholds keyed by (shover_type, number_already_in, number_behind), for example vs any-two shover alone: 22+, A2+, K9+; + tight caller: QQ+, AK; + any-two caller: 77+, AT+, KQ.

---

## 2. `multiway-bluff-cbet` (rank 2)

**Description.** Continuation-bet or barrel bluffs that ignore the number of opponents and their type. P(all fold) = product of the individual fold probabilities. Three opponents folding 60% each fold together only 22%. Against Station (about 30% fold when missed, 0% when it hit anything) and Limper, a 2/3-pot c-bet into 3 players gets through maybe 5–10% of the time, but needs 40%.

**Why it costs bb/100 (hypothesis).** In a loose field the preflop raiser sees a 3+ way flop in perhaps 50–70% of raised pots. If hero raises about 20% of hands, that is 10–14 multiway flops per 100 hands, and about 65% of them miss: about 7–9 spots. A missed c-bet of 0.67×pot (pot about 10bb) with 10% fold equity and about 20% realised equity when called costs about 3–4bb each. Total: about 15–30 bb/100 if the incumbent c-bets every flop, and about 5 bb/100 if it already scales somewhat.

**Reproducible test.**
- Table: Hero, Station ×3, Limper ×3, Nit ×1. Hero should open often and get multiway flops.
- Variant (control): Hero, Nit ×6, Limper ×1. Here bluffs should work, which guards against overcorrecting into never bluffing.
- Metric: hero's flop c-bet frequency split into "missed board" and "pair+", by number of opponents (1, 2, 3+). Report bb won/lost on c-bets when missed. Expected-good behaviour: missed c-bet frequency close to 0 with 3+ players that include a station; still positive heads-up vs Nit.

**Impact / likelihood.** 5–30 bb/100; likelihood **med-high** (default "c-bet if preflop aggressor" rules are very common).

**Fix ideas.**
1. Bluff gate: estimate p_fold_i per live opponent (from observed fold-to-bet counts, prior 0.45 for unknown, 0.1–0.3 for a seat with VPIP > 50% and fold-to-cbet < 30%). Bluff only if Π p_fold_i ≥ bet / (pot + bet) − equity_when_called_bonus. In practice this means essentially never bluffing into 3+, or into any station.
2. Use the freed frequency for value: with 2+ callers, bet only pair+ or strong draws (combo draws keep fold equity plus about 50% raw equity).

---

## 3. `limper-iso-and-squeeze` (rank 3)

**Description.** The opening strategy ignores limpers and callers. (a) Hero opens to a fixed 2.5–3bb behind 2–3 limpers, so a premium plays a 5-way pot (AA drops from 84% heads-up to 56% vs 4 hands; AKo 66% → 38% vs 3). (b) Hero iso-raises light (KJo, A5o) against stations who never fold, which creates bloated multiway pots with dominated hands. (c) Hero misses squeeze-for-value spots (open + 2 callers, hero holds QQ+/AK, and loose callers call a big squeeze with worse) and makes light squeezes that cannot work against stations and get stacked by shovers.

**Why it costs bb/100 (hypothesis).** Limped pots happen in maybe 30–50% of hands at this table. Correct sizing (3bb + 1–1.5bb per limper, more vs stations, since stations' calls are price-insensitive) turns premiums into heads-up or 3-way pots with bigger pots. For value hands (top about 8%, roughly 8 per 100 hands, half of them with limpers ahead), an extra 2–4bb won per hand when called by a worse range gives about 5–12 bb/100. Avoiding light isos with dominated hands saves another 2–5 bb/100.

**Reproducible test.**
- Table: Hero, Limper ×4, Station ×2, Nit ×1. Limper limps about 75% and calls raises ≤4bb with chen≥5.
- Squeeze table: Hero, Nit-like opener (raises 3bb with chen≥7), Station ×3, Limper ×2, plus seat 7 run twice: once as Limper, once as RandomShover. The RandomShover run checks that light squeezes get punished.
- Metric: hero's raise-to amount as a function of limpers; number of players seeing the flop when hero raises; bb/100 broken down by hand class (premium, medium, speculative) and by limper count. Compare with a reference policy: iso to (3 + 1.5 × limpers) bb with a value range only vs stations (chen≥8); vs folders also add light isos in position.

**Impact / likelihood.** 5–15 bb/100; likelihood **high** (fixed open sizes are the default for most bots).

**Fix ideas.**
1. Size = base 3bb + k × limpers (k = 1 vs folders, 1.5–2 vs stations), +1bb out of position. Squeeze size = 4 × open + 1 × open per caller. Iso range narrows when the limpers are stations (value-only, chen≥8), widens in position vs folders.
2. Over-limp/call (do not iso) with small pairs and suited connectors behind 2+ stations: cheap multiway pots where implied odds are best (see problem 6).

---

## 4. `multiway-value-sizing` (rank 4)

**Description.** Two-sided leak. (a) Under-betting value hands (sets, two pair, overpairs on dry boards) against several stations: they call without regard to size, so bigger bets (pot, overbet on the river) earn more. Checking back thin value because "3 opponents might have it" gives up bets that 2–3 calling stations would pay with worse. (b) Over-valuing one pair: top pair with a weak kicker goes from 85% vs 1 random hand to 61% vs 3 random. Ranges that *call* multiway are stronger than random, so stacking off with one pair in a 3–4-way pot against a bet-and-raise is a big loser. Stations rarely raise, so a raise from one is near-nuts.

**Why it costs bb/100 (hypothesis).** Hero has two pair or better on the river in a multiway pot maybe 3–5 times per 100 hands. Betting 1× pot instead of 1/3 pot against 2 stations who call about 80% gains about 2 × 0.8 × (0.67 × pot ≈ 10–20bb) ≈ 15–30bb per spot, so about 5–15 bb/100. Each one-pair stack-off vs a station raise is about −50 to −90bb; at 0.1–0.2 per 100 hands that is about 5–15 bb/100.

**Reproducible test.**
- Table: Hero, Station ×4, Limper ×2, Nit ×1.
- Add a "StationRaiser" variant: Station that raises (pot-size) only with two pair+ on the flop or turn and otherwise calls. This tests whether hero respects a passive player's raise.
- Metric: average river bet / pot when hero holds two pair+ and 2+ opponents are live; showdown value of hero's one-pair hands in pots ≥ 50bb; hero's fold frequency vs a StationRaiser raise with top pair. Expected-good: bigger bets with strong hands vs stations; folding top pair to a passive bot's raise in multiway pots.

**Impact / likelihood.** 5–15 bb/100; likelihood **med** (equity-vs-random bots overvalue one pair; fixed-fraction bettors under-size vs stations).

**Fix ideas.**
1. Size by opponent call-elasticity: if all live opponents have a fold-to-bet rate < 30%, use 0.9–1.2 × pot for value with two pair+, and 0.5 × pot with top pair (thin value is good vs stations). Otherwise use standard sizes.
2. Range-conditioned equity: compute equity vs the *calling/raising* range (passive bot raise → top 5% of hands that reach the street), not vs random. Simplest version: an "aggression from passive seat" flag that caps hero at calling or folding with one pair.

---

## 5. `oop-realization-blind-defense` (rank 5)

**Description.** Calling preflop raises out of position (especially from the SB, or cold-calling in early position) with hands that realise poorly multiway OOP (offsuit broadways that get dominated, weak aces). Also misusing BB pot odds: defending based on price alone while ignoring that 2–3 callers behind the raise make dominated offsuit hands much worse. KJo has 28% vs 4 random hands but far less vs real calling ranges, and it plays OOP. Mirror leak: folding too much in position vs limps and min-raises, giving up cheap, well-realised spots.

**Why it costs bb/100 (hypothesis).** SB/BB are 25% of hands. If hero cold-calls or defends 10–15% too wide OOP into multiway pots at −1 to −3bb each, that is about 3–8 bb/100. A rough check: equity realisation OOP multiway is about 70–80% for offsuit broadways vs about 100%+ for suited or connected hands in position.

**Reproducible test.**
- Table: Hero, an "Opener" bot that raises to 3bb with chen≥6 from any seat, Limper ×3 (who call raises wide), Station ×2, Nit ×1.
- Fix hero to the SB and BB for a dedicated run (or filter the logs by hero position).
- Metric: VPIP / bb/100 by position × number of callers already in. Flag hands where hero calls OOP with offsuit non-pair, non-ace-suited hands and loses. Compare with a reference: SB 3-bet-or-fold vs opens; BB defends with suited, connected and paired hands by price, and fewer offsuit broadways when 2+ callers are already in.

**Impact / likelihood.** 3–10 bb/100; likelihood **med** (many bots have position-blind preflop charts).

**Fix ideas.**
1. Position- and caller-count-aware preflop tables: separate charts for (IP/OOP) × (0, 1, 2+ callers). OOP prefers 3-bet-or-fold; multiway prefers suitedness and pairs over offsuit broadways.
2. A postflop realisation discount: when OOP in 3+-way pots, require equity + 10% before calling bets without a pair-plus-draw or better.

---

## 6. `implied-odds-setmine` (rank 6)

**Description.** Small pairs flop a set 12% of the time (7.3:1 against). Deep (100bb), against stations who pay off with top pair or overpairs, calling raises of up to about 5–7% of effective stack is profitable on implied odds alone. Typical bots either fold 22–66 to any raise (losing this edge) or call raises from **shovers / short commitments**, where there are no implied odds. Calling a 3bb open from a bot that will shove 100bb on any flop is a different situation: the decision becomes a pure equity call. Also relevant: suited connectors have only 19% vs 4 random hands (below the 20% fair share). They profit only through implied odds vs stations, and lose vs aggressive bots.

**Why it costs bb/100 (hypothesis).** Pocket pairs are about 6% of hands. Facing a raise with 22–88 multiway happens maybe 2–3 per 100 hands. Each correct set-mine call vs a station earns about +2–5bb (0.12 × average stack-off of about 40–60bb − 0.88 × 3bb). That gives about 2–8 bb/100 if the incumbent folds these. Calling vs a RandomShover raise and then folding to the flop shove costs roughly the same.

**Reproducible test.**
- Table A (implied odds present): Hero, Nit-opener (raises 3bb with chen≥7, then stacks off postflop with overpair or top pair top kicker), Station ×3, Limper ×2.
- Table B (no implied odds): replace the Nit-opener with RandomShover (p=0.5 of shoving each postflop street) and add a Shover.
- Metric: hero's call frequency with 22–88 and suited connectors facing raises ≤ 4bb in A vs B; bb/100 on those hands. Expected-good: calls in A, folds or pure-equity decisions in B.

**Impact / likelihood.** 2–8 bb/100; likelihood **med**.

**Fix ideas.**
1. Implied-odds rule: call with a pocket pair iff to_call ≤ min(eff_stack_vs_raiser, eff_stack_vs_likely_payer) / 15 and at least one live opponent is modelled as a "pays off" type (fold-to-bet < 35% postflop). If the raiser is classified as a shover, decide by raw equity instead.
2. Postflop discipline: with an unimproved small pair on a multiway flop, check/fold (no "floats"); with a set vs stations, bet big every street (links to problem 4).

---

## 7. `allin-closed-action-robustness` (rank 7; formerly "side-pot-awareness")

**Key observation.** All stacks reset to 2,000 every hand, so stacks are always equal. Once anyone is all-in for 100bb, anyone who continues must also be all-in. **Uneven side pots cannot occur under the current rules.** The only "side money" is dead money from players who folded. So classic side-pot leaks (bluffing a side pot, capped pot odds against a short stack) are **not relevant now**. They become relevant only if the official rules turn out to use persistent stacks, so re-check when the rules arrive. What remains:
(a) Robustness when facing an all-in: `'raise'` is not in `legal` and `min_raise_to`/`max_raise_to` may collapse. A bot that hard-codes `raise to min_raise_to` with a premium, or raises when `to_call >= stack`, emits illegal actions. The engine then folds for us, which means folding AA to a shove: a catastrophic loss of the whole pot.
(b) Hands where hero is all-in (or everyone is): `act` may still be called (or not), with `to_call == 0` and only `check` legal. The bot must not crash.
(c) If persistent stacks are confirmed, reinstate the side-pot items: fold equity only applies to pot layers whose contestants can still fold, and the winnable amount is capped per player.

**Why it costs bb/100 (hypothesis).** (a) Shoves happen on most hands when a Shover is seated. If hero's premium-hand path tries an illegal raise even 1% of the time when facing a shove, the engine folds a hand with about 65–85% equity in a pot of about 100bb or more, about −60bb each. At about 1–3 such spots per 100 hands, that is roughly 1–5 bb/100, plus robustness-gate failures in Phase 3.

**Reproducible test.**
- Table: Hero, Shover ×2, Station ×2, Limper ×2, Nit ×1. 20k hands.
- Unit-style probe (no table needed): feed hero synthetic `obs` with `to_call = 1990` (hero stack 2000 minus a 10 SB post), `legal=['fold','call']`, `min_raise_to = max_raise_to = 2000`, holding AA/KK/AKs. Also feed one with `legal=['check']`, `to_call=0`, `stacks[hero]=0`, `all_in[hero]=True`.
- Metric: robustness counters (illegal actions or exceptions = 0); hero never folds AA/KK vs a single any-two shove.

**Impact / likelihood.** 1–5 bb/100 plus a gate risk now; likelihood **low-med**. Side-pot strategy leaks: about 0 under the current rules, med if stacks turn out to be persistent.

**Fix ideas.**
1. Action sanitizer as the last step of `act`: choose only from `obs.legal`; clamp amount to [min_raise_to, max_raise_to]; if the chosen raise has amount ≥ max_raise_to or 'raise' is not legal, map it to call (or check); wrap the whole `act` in try/except → `call` if facing a bet with hand-strength ≥ threshold, else check/fold.
2. (Persistent-stacks contingency) Compute pot layers from per-seat total commitments in `history`; apply fold equity only to layers with live foldable contestants.

---

## Cross-cutting recommendation (hypothesis)

Most of these leaks share one root cause: **decisions ignore the number and type of live opponents**. A lightweight per-seat profile built in `observe` would feed fixes 1–6 at once. Track VPIP, PFR, all-in frequency, fold-to-bet and showdown hands, and classify each seat as shover / station / limper / nit / unknown with Bayesian priors and about 30 hands of warm-up. Solvers should build this as a shared helper but must keep defaults safe when a seat is still "unknown".
