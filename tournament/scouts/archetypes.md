# Scout report: simple opponent archetypes

Angle: the cheap bots a weekend student field tends to produce (always-all-in, random-timer shover, calling station, nit, maniac, tight-passive, min-raise spammer, limp-everything, few-size equity-threshold bots), and where a **reasonable baseline** loses bb/100 against them.
Game: 7–8 players, 2,000 chips (100bb), 10/20, stacks reset every hand, scored in bb/100.

**Every strategy claim below is a hypothesis until the arena confirms it.** The numbers come from rough reasoning plus a quick standalone Monte Carlo check (method at the bottom). Treat them as orders of magnitude, not measurements.

---

## 0. Shared definitions

### 0.1 Helpers used in the pseudocode
- `pct(hole)`: percentile of the 169-class hand in an "equity vs one random hand" ordering, where 0.0 is best (AA) and 1.0 is worst (32o). Rough cut-offs from the MC: top 2.6% ≈ QQ+, AK; 10% ≈ 77+, ATo+, KJo+, KQs, AJs+; 20% ≈ 55+, A6o+, A2s+(most), KTo+, QJs; 40% ≈ any pair, any ace, K3o+, Q6o+, J7s+, T9s; 50% ≈ K2o, Q2o+ and similar.
- `eq(hole, board, n)`: MC equity vs `n` uniformly random hands (the evaluator helper).
- `pos(obs)`: seat position relative to the button (UTG … BTN, SB, BB).
- `nraises(obs)`: number of `raise` actions this street from `obs['history']`.
- `bet_to(frac)`: `min(max_raise_to, max(min_raise_to, max(bets) + frac*(pot + to_call)))`, i.e. a raise-to total. The contract has no separate `bet` action; opening a street is a `raise`.
- Every dummy has to clamp amounts to `[min_raise_to, max_raise_to]`, use only actions in `legal`, and check (never fold) when `to_call == 0`.

### 0.2 B0: the baseline filler / reference bot (what "a reasonable baseline" means here)
```
OPEN = {UTG:.12, UTG1:.14, MP:.17, HJ:.22, CO:.28, BTN:.45, SB:.35}
act(obs):
  p = pct(hole)
  if street == 'preflop':
    r = nraises(obs)
    if r == 0:
      if pos == BB and to_call == 0: return check
      if p <= OPEN[pos]: return raise(min(max_raise_to, 2.5*bb + 1*bb*limpers))
      return fold
    if r == 1 and not facing_all_in:
      if p <= 0.026: return raise(3 * current_bet)          # 3-bet QQ+/AK
      if p <= 0.08:  return call
      if pos == BB and p <= 0.25 and to_call <= 2.5*bb: return call
      return fold
    # 2+ raises, or facing an all-in
    if p <= 0.026: return raise(max_raise_to) if 'raise' in legal else call
    return fold
  else:
    e = eq(hole, board, 1)            # deliberately vs ONE random hand (the common shortcut)
    if to_call == 0:
      return raise(bet_to(0.66)) if e > 0.65 else check
    po = to_call / (pot + to_call)
    if e > 0.88 and 'raise' in legal: return raise(min(max_raise_to, 3*to_call + max(bets)))
    return call if e >= po else fold
```
Unless it says otherwise, "baseline" below means B0. The incumbent may differ, so each scenario measures the **candidate vs B0 in the same seat** (duplicate deals, seat rotation) and reports candidate bb/100.

---

## P1. `shove-call-range-too-tight` (rank 1)

**Description.** A chart-style baseline treats a 100bb jam as "facing a 4-bet or all-in" and continues only with something like QQ+/AK, maybe JJ+/AQ+. Against an always-all-in or random-timer shover the jamming range is **random**, so with no one else left in the hand the break-even call needs about 49.5% equity: call 1,980–2,000 to win about 4,010–4,030. Roughly the **top 40–50% of hands** clear that bar (any pair, any ace, most Kx, Q6o+, …).

**Why it costs bb/100 (hypothesis, MC-supported).** Preflop-only MC, 8 seats: 1 always-shover acting first, 6 B0-style callers (call the jam only with QQ+/AK), candidate in a random position. 60k hands per policy, common random numbers, cell SE about ±25 bb/100. Candidate's EV from calling vs always folding:

| Candidate calls jam with | 1 shover at table | 2 shovers at table |
|---|---|---|
| QQ+/AK (2.6%) | +134 | +207 |
| top 10% | +324 | +483 |
| top 20% | +483 | +689 |
| top 30% | +575 | +834 |
| top 40% | +602 | +852 |
| top 50% | +600 | +872 |

(These rows all tighten to QQ+/AK once a non-shover has already called. See P2.)
- So at a table with one always-shover, B0-style tightness leaves roughly **+300 to +470 bb/100** on the table. The optimum is flat from about the top 35% to the top 50%.
- A random-timer shover (U{1..15}, about 1 shove per 8 hands) has the same random range at 1/8 the frequency, so the gap is **≈ 35–60 bb/100 per timer bot at the table**.
- **Timer trap.** If the timer bot check/folds between shoves, its shoves are its only VPIP (about 12%). A VPIP/PFR opponent model will label it a *nit* and fold *more* to its jams. Showdowns, though, reveal random hands.
- Postflop shoves (a per-action timer that fires on the flop/turn/river) carry the same random range. A baseline that discounts equity for "overbet = strength" folds there too.

**Test scenario.**
```
ALWAYS_SHOVE.act(obs):
  if 'raise' in legal: return {'action':'raise','amount':max_raise_to}
  if 'call'  in legal: return {'action':'call'}
  return {'action':'check'}

TIMER_SHOVE(mode='per_hand'|'per_act', idle='checkfold'|'checkcall'):
  __init__: rng = Random(rng_seed); counter = rng.randint(1,15)
  observe(ev): if mode=='per_hand' and ev.type=='hand_start': counter -= 1
  act(obs):
    if mode=='per_act': counter -= 1
    if counter <= 0 and 'raise' in legal:
        counter = rng.randint(1,15); return raise(max_raise_to)
    if counter <= 0 and 'call' in legal:          # can't raise (already all-in facing): call
        counter = rng.randint(1,15); return call
    if idle=='checkfold': return check if to_call==0 else fold
    else:                 return check if to_call==0 else call
```
Table mixes (8 seats, rotate seats, duplicate deals, at least 20k hands):
- S1a: 1 ALWAYS_SHOVE + 6 B0 + candidate
- S1b: 2 ALWAYS_SHOVE + 5 B0 + candidate
- S1c: 1 TIMER_SHOVE(per_hand, checkfold) + 6 B0 + candidate (needs ~50k hands; signal is about 1/8 of S1a)
- S1d: 1 TIMER_SHOVE(per_act, checkcall) + 6 B0 + candidate (postflop shoves)

Pass bar: candidate within ~10% of the "top-40% caller" oracle in S1a, and it must not fold more to the timer bot than to the always-shover once it has seen showdowns.

**Impact / likelihood.** +300–470 bb/100 at an always-shover table, +35–60 per timer bot. **Likelihood high**: CONTEXT names both archetypes explicitly.

**Fix ideas.**
1. Per-seat jam-range model: shove frequency plus the percentile of hands it showed at showdown. Prior "random" once shove% > 30% or any shown jam hand is below the top 40%. Call when equity vs (inferred jam range + likely callers behind) > pot odds.
2. Cheap patch: if a seat has jammed ≥ 3 times and its average shown `pct` > 0.35, call jams from that seat with the top 40% (tightened per P2).

---

## P2. `shover-multiway-discipline` (rank 2)

**Description.** With a shover at the table nearly every hand becomes a preflop all-in-or-fold spot, and the correct ranges depend on **who has already called and who is still behind**. A baseline (or a naive P1 fix) goes wrong three ways:
(a) **Overcalling** a jam after a tight player has already called. You are now drawing against QQ+/AK plus a random hand.
(b) **Open-raising into a shover still to act** with hands it will then fold to the jam. The 2.5bb open just burns.
(c) Missing **dead money**. When the shover acts behind you, limping your calling range (and letting others limp and then fold) adds dead chips to the all-in pot. Raising only folds out the players who would have donated.

**Why it costs bb/100.** Same MC as P1: calling the top 40% *regardless* of an earlier premium caller scored +505 vs +602 for tightening to QQ+/AK, so about **−100 bb/100** for (a). For (b): the candidate acts before the shover in about half its hands. B0 opens about 20% of those and folds about 85% of its opens to the jam, so ≈ 10 × 0.85 × 2.5bb ≈ **−20 bb/100**. (c) is a hypothesis, probably +5–15 bb/100.

**Test scenario.**
- S2a: 1 ALWAYS_SHOVE + 6 B0 + candidate. Log candidate EV split by (# callers before candidate) and (opened, then folded to jam).
- S2b: 1 ALWAYS_SHOVE + 3 B0 + 3 STATION_PURE (see P3) + candidate. Stations overcall jams with anything, so multiway all-ins are common and the candidate's calling range should *widen toward the 3-way break-even (~33% equity vs two random hands)* when the other callers are random-range too. This tests that the fix depends on the callers' ranges, not just their count.

**Impact / likelihood.** 30–120 bb/100 at a shover table. **Likelihood high** when P1 applies.

**Fix ideas.**
1. Compute equity vs the *actual set of called ranges* (random for shover/station seats, tight for chart seats). Require equity > `call/(pot+call)` and shade down by the probability that someone behind overcalls.
2. With a known always-shover yet to act: fold hands below the call threshold, limp hands above it. Never open-raise a hand you would fold to the jam.

---

## P3. `station-value-cap` (rank 3)

**Description.** Fixed 1/2–3/4-pot sizing grows the pot geometrically and caps value. From a 6.5bb single-raised pot, three 3/4-pot bets put only ≈ **50bb** of the 97bb behind into the pot, while pot-sized bets or a jam get all 100bb in. A calling station's range is close to random and it calls almost any size, so every bet with equity > 50% is pure value and **EV scales linearly with size**. B0 also open-raises small (letting stations limp along and making pots multiway) and its "bet if e > 0.65 vs random" can include semi-bluffs that never get folds.

**Why it costs bb/100 (hypothesis).** Heads-up vs a pure station on the flop with equity e vs random:
- 3/4-pot line: ≈ (2e−1) × 47bb
- max-size line: ≈ (2e−1) × 97bb
- At e = 0.8 the gap is **≈ +30bb per instance**. At e = 0.65 it is ≈ +15bb (smaller after accounting for B0 being able to check/fold when the turn goes bad).

The station calls every open, so the candidate is HU-or-multiway with it in nearly every pot it enters (about 20 hands/100), and it holds e > 0.65 on maybe half of those flops. That gives a raw ceiling of **≈ +100–250 bb/100** vs a *pure* station, and much less vs a "sticky" one that folds to jams. Preflop: an AA jam vs a station's random call ≈ +70bb, vs maybe +25–35bb from a 2.5x open plus 3/4-pot play.

**Test scenario.**
```
STATION_PURE.act(obs):
  return check if to_call == 0 else call          # never folds, never raises

STATION_STICKY.act(obs):
  if to_call == 0: return check
  e = eq(hole, board, 1) if board else 1 - pct(hole)
  if to_call <= pot: return call                   # calls anything up to pot
  return call if e > 0.5 else fold                 # big bets/jams: calls with ~half its hands
```
- S3a: 1 STATION_PURE + 6 B0 + candidate
- S3b: 2 STATION_STICKY + 5 B0 + candidate
- S3c: 3 STATION_PURE + 4 B0 + candidate (multiway value: equity vs several random hands; see P6)

Metric: candidate bb/100, plus average pot size when the candidate wins at showdown vs a station.

**Impact / likelihood.** 20–150 bb/100 depending on station purity. **Likelihood high**: calling stations are among the easiest bots to write.

**Fix ideas.**
1. Per-seat fold-to-bet estimate. When a seat's fold% < ~15% and it is the main opponent: size value bets geometrically to reach all-in by the river (or jam once e vs its range > 0.6), zero bluffs, thinner value (top pair weak kicker bets three streets).
2. Preflop iso-raise vs stations/limpers: 4–5bb + 1.5bb per limper with the value range, tighter opening range otherwise.

---

## P4. `raise-war-surrender` (rank 4)

**Description.** B0's preflop logic keys on **raise count** (open / 3-bet / 4-bet+) and assumes standard-strength ranges. Against a **min-raise spammer** (min-raises every chance with any hand) or a **maniac** that re-raises most hands without jamming, B0 opens, gets re-raised cheaply, and folds the "vs 3-bet" chart. It loses its open while getting 4:1+ odds, and folds hands that are 60%+ vs a random range. Against a pure always-min-raiser, *any* raise war climbs to all-in, so the spot is effectively P1 with extra steps. Against a maniac, B0 also under-defends the BB and folds top pair to repeated pot-sized aggression if it applies any "big bet = strength" discount.

**Why it costs bb/100 (hypothesis).** With the spammer behind about half the time: B0 opens about 20% of those hands and folds about 85% to a min re-raise, losing 2.5bb each, ≈ **−20 bb/100** in direct burn. Missed value is larger: B0's opening range averages about 62% equity vs random, and against a pure min-raiser stacks would go in, so ≈ (2·0.62−1)·100bb ≈ 24bb per surrendered hand. That is a ceiling of **≈ +100–200 bb/100 vs a pure spammer**, and maybe 15–40 vs a capped spammer or maniac. BB defence vs a min-raise only needs ≈ 22% equity, so near-100% defence is fine, and B0 folds about 75%.

**Test scenario.**
```
MINRAISE_SPAM(cap=None|1):
  act(obs):
    raised_this_street = count own raises this street
    if 'raise' in legal and min_raise_to < max_raise_to and (cap is None or raised_this_street < cap):
        return raise(min_raise_to)
    if 'call' in legal: return call
    return check

MANIAC (non-all-in):
  __init__: rng = Random(rng_seed)
  act(obs):
    if 'raise' in legal and rng.random() < 0.75:
        tgt = max(bets) + (pot + to_call)                 # pot-size raise-to
        tgt = min(tgt, 0.6 * (stacks[seat] + bets[seat]))  # never jams voluntarily
        if tgt >= min_raise_to: return raise(tgt)
    if to_call == 0: return check
    return call if (to_call <= pot or rng.random() < 0.5) else fold
```
- S4a: 1 MINRAISE_SPAM(cap=None) + 6 B0 + candidate
- S4b: 1 MINRAISE_SPAM(cap=1) + 6 B0 + candidate
- S4c: 1 MANIAC + 6 B0 + candidate
- S4d: 2 MANIAC + 5 B0 + candidate (multiway escalation and squeeze dynamics)

Metric: candidate bb/100, plus the count of "candidate put in ≥ 2.5bb then folded preflop".

**Impact / likelihood.** 15–200 bb/100 (low end for maniac/capped, high end for pure spammer). **Likelihood medium**: "always raise min" and "raise most hands" are common first bots, though not as common as shovers and stations.

**Fix ideas.**
1. Decide on **price and villain range, not raise count**: continue if equity vs the raiser's inferred range (from its raise frequency) > `to_call/(pot+to_call)` adjusted for position. Detect "raises > 50% of hands" seats and widen 3-bet/4-bet/stack-off ranges to the top 30–40%.
2. Vs maniacs, trap: flat or check strong hands when the maniac acts behind and let it bet. Call down wider postflop and stop bluffing into it.

---

## P5. `aggression-blind-equity` (rank 5)

**Description.** B0's postflop decisions use equity vs a **random** hand regardless of what the opponent has done. Against **nits / tight-passive / few-size threshold bots**, a bet or raise means a strong range. For example, AK on K-8-3-2-5 has about 90% equity vs random but under 10% vs {sets, two pair, straights}. B0 still calls pot-sized river raises because 90% > 33%, so it pays off the entire value range at full price. The mirror leak: any heuristic "strength discount" gets applied to maniacs too, so it folds too much against them. Equity-threshold bots with 2–3 bet sizes also leak strength through size (e.g. pot = e > 0.8, half pot = e > 0.6), which B0 ignores.

**Why it costs bb/100 (hypothesis).** A tight-passive bot only puts in big money with two pair or better. Suppose B0 pays off 1–3 such spots per 100 hands at about 20–40bb each, offset slightly by the occasional real win. Net **≈ −10 to −40 bb/100** per strong-range bot at the table. The size-tell edge vs threshold bots is maybe 3–10 bb/100.

**Test scenario.**
```
TIGHT_PASSIVE:
  act(obs):
    if street == 'preflop':
      p = pct(hole)
      if p <= 0.03 and 'raise' in legal and nraises(obs) == 0: return raise(3*bb)
      if p <= 0.20: return check if to_call == 0 else (call if to_call <= 4*bb or p <= 0.05 else fold)
      return check if to_call == 0 else fold
    e = eq(hole, board, 1)
    if e > 0.92 and 'raise' in legal: return raise(bet_to(1.0))   # only nut-ish hands bet/raise, pot size
    if to_call == 0: return check
    return call if e > 0.70 else fold

NIT (folds-too-much):
  preflop: play only p <= 0.06 (raise 3bb if unopened, else call/3-bet with p <= 0.026); else check/fold
  postflop: e = eq(hole, board, 1); bet pot if e > 0.90; call if e > 0.80; else check/fold

THRESHOLD_BOT:
  act(obs):
    n = number of non-folded opponents
    e = eq(hole, board, n) if board else (1 - pct(hole))
    if to_call == 0:
      if e > 0.80: return raise(bet_to(1.0))
      if e > 0.60: return raise(bet_to(0.5))
      return check
    po = to_call / (pot + to_call)
    if e > 0.90 and 'raise' in legal: return raise(3*to_call + max(bets))
    return call if e >= po else fold
```
- S5a: 2 TIGHT_PASSIVE + 4 B0 + 1 STATION_PURE + candidate (the station keeps pots going)
- S5b: 2 NIT + 2 THRESHOLD_BOT + 3 B0 + candidate
- S5c, control for over-correction: 2 MANIAC + 5 B0 + candidate. The fix must not fold more here.

Metric: candidate bb/100, plus EV of candidate calls facing a bet/raise ≥ 1/2 pot, split by aggressor archetype.

**Impact / likelihood.** 10–40 bb/100. **Likelihood high**: tight-passive and threshold bots are the default "sensible" student bot.

**Fix ideas.**
1. Per-seat aggression model (AF, bet% by street, showdown strength of bet/raise hands). Compute equity vs a range narrowed by the seat's observed bet-threshold, e.g. vs the top `bet%` of hands rather than random.
2. Simple patch: a size-to-strength table per seat learned from showdowns. Fold medium made hands to a big raise from a seat whose aggression frequency < 10%.

---

## P6. `multiway-equity-overestimate` (rank 6)

**Description.** Limp-everything and calling-station bots make 4–6-way pots common at 7–8 handed. B0 bets and calls based on equity vs **one** random hand, which badly overstates multiway strength. MC on K♥7♠2♦ (equity vs 1 / 2 / 4 random hands):

| Hand | vs 1 | vs 2 | vs 4 |
|---|---|---|---|
| 99 | .72 | .54 | .30 |
| 87s (middle pair) | .71 | .51 | .29 |
| K5s (top pair, weak kicker) | .85 | .72 | .53 |
| AK | .90 | .80 | .65 |
| A5h, nut flush draw (on K♥7♥2♦) | .67 | .52 | .41 |

B0 value-bets 99 (0.72 > 0.65) into four limpers with 30% real equity and calls bets with it. It also iso-raises only 2.5bb + 1bb per limper, which keeps pots multiway. Conversely, it under-values draws in multiway pots, where implied odds are good.

**Why it costs bb/100 (hypothesis).** Maybe 3–8 multiway pots per 100 hands where B0 bets or calls with second-best one-pair hands, at about 3–8bb each: **≈ −10 to −30 bb/100** at limp-heavy tables.

**Test scenario.**
```
LIMPER:
  act(obs):
    if street == 'preflop':
      if to_call == 0: return check
      if to_call <= bb: return call                       # limp any two
      return call if to_call <= 4*bb else (call if pct(hole) <= 0.10 else fold)
    e = eq(hole, board, 1)
    if to_call == 0: return check                        # never bets
    po = to_call / (pot + to_call)
    return call if e >= po + 0.05 else fold              # calls with any pair / draw vs normal sizes
```
- S6a: 4 LIMPER + 3 B0 + candidate
- S6b: 3 LIMPER + 2 STATION_STICKY + 2 B0 + candidate

Metric: candidate bb/100, plus EV in pots with ≥ 4 players seeing the flop.

**Impact / likelihood.** 10–30 bb/100. **Likelihood medium-high**.

**Fix ideas.**
1. Use `eq(hole, board, n_active_opponents)` (or equity vs per-seat ranges) everywhere. Raise value thresholds with the number of players. Prefer pot control with one-pair hands multiway and play draws more aggressively.
2. Iso-raise to 4bb + 1.5bb per limper (bigger vs known stations), or limp behind speculative hands in position.

---

## P7. `nit-fold-equity-unused` (rank 7)

**Description.** Against folds-too-much bots the fixed opening chart and equity-only postflop betting never use fold equity. Two examples: when nits sit in the blinds and fold more than 85%, opening any two from BTN/CO/SB is profitable, and when a nit checks to you heads-up, a small c-bet with air prints. B0 bets only with equity > 0.65, so it never bluffs, and it opens only 45% on the BTN.

**Why it costs bb/100 (hypothesis).**
- **Steal.** Risk 50 chips to win 30, with both blinds folding about 90%, so success ≈ 0.81. EV ≈ 0.81·30 − 0.19·60 ≈ +13 chips (+0.65bb) per extra steal. Extra steal hands: about 55% of BTN hands, 40% of CO, 50% of SB, which comes to ≈ **+4–8 bb/100**.
- **C-bet vs nit.** A nit folds unpaired hands about 65% of the time. A 1/3-pot bet with air in a 5.5bb pot: 0.65·5.5 − 0.35·1.8 ≈ +3bb, vs about +0.8bb from checking. At maybe 2 spots/100 that is ≈ **+4 bb/100**.

**Test scenario.**
- S7a: 3 NIT (spec in P5) + 4 B0 + candidate. Rotate seats so nits often sit in the blinds relative to the candidate.
- S7b: 2 NIT + 2 TIGHT_PASSIVE + 3 B0 + candidate

Metric: candidate bb/100, steal success %, and c-bet fold % vs nit seats.

**Impact / likelihood.** 5–15 bb/100. **Likelihood medium**: some nits will exist, but often as part of threshold bots.

**Fix ideas.**
1. Per-seat fold-to-open / fold-to-cbet tracking. Widen steals when both remaining players behind fold more than 80%, and c-bet small with any two vs high fold-to-cbet seats (never vs stations; see P3).
2. Keep it gated by sample size (around 30 or more observations) so it doesn't misfire early in a match.

---

## Cross-cutting notes (hypotheses)
- **One per-seat model fixes most of these.** Track, per seat: VPIP, PFR, jam%, fold-to-bet%, AF, and showdown hand percentiles bucketed by the action taken. That supports P1, P2, P3, P4, P5 and P7. Showdown percentiles matter most: they separate *random-but-rare* (timer shover) from *tight* (nit), which frequency stats alone confuse.
- **Archetype classification can be coarse.** Five labels cover nearly all of it: {jammer, station, hyper-aggro, tight/strong-when-betting, unknown→B0}. Errors are asymmetric: treating a nit as a jammer is far costlier than the reverse, so require showdown evidence before widening calls.
- **The table changes everyone's ranges.** With one always-shover at the table, nearly all hands are preflop all-in-or-fold, and postflop skill barely matters there. With stations or limpers, pots go multiway and P6 dominates. The candidate should condition on the table mix, not just on the current aggressor.
- **Variance warning for the arena.** Jam-heavy tables have a per-hand SD around 60–100bb. Separating policies that differ by 20 bb/100 needs ~50k+ hands or duplicate deals with common seeds.

## Method behind the numbers
Throwaway scripts in `/tmp`, not part of the repo:
- Equity vs random hands: 1,500 MC samples per 169-class, giving the percentile ordering.
- Jam simulation: 8 seats, 1–2 always-shovers acting first, 6 other seats calling the jam only with QQ+/AK, candidate in a uniformly random position. Every caller goes to showdown, with 30 chips of dead blinds. EV is relative to always folding. 60k hands per cell, common random numbers across policies, SE about ±25 bb/100 per cell (policy differences are tighter).
- Multiway flop equities: 4,000 MC samples each.

Simplifications: the jam sim ignores opens made before the shover acts and the blind each player has already posted, and the postflop figures (P3–P7) are analytic estimates only. The arena scenarios above are the real test.
