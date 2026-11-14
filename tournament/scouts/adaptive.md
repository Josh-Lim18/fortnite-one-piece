# Scout report: adaptive / opponent-modelling opponents

Angle: threshold-rule exploiters, slow and fast learners, copycats, table-wide adapters, deceivers who set up a pattern and then reverse it, and the matching risks for OUR model: being taught, then exploited, and model poisoning.

Our bot, as assumed here: a balanced-ish baseline, plus an opponent model with per-situation stats (fold-to-cbet, VPIP/PFR, 3bet, AF, WTSD, bluff ratio at showdown, ...), confidence weight `w = n/(n+k)`, recency decay (half-life H hands), and a safety budget that caps how far we deviate from the baseline.

**Everything below is a hypothesis.** The bb/100 figures are back-of-envelope estimates and none has been tested in the arena yet. No incumbent code was in the repo when I wrote this, so the problems target the architecture described above, not any specific implementation.

---

## 0. Background numbers used throughout (hypotheses)

- **Sparse per-opponent data.** At 8-handed we are the preflop raiser in roughly 15% of hands, and we reach a heads-up flop as raiser in about 9% of hands. That gives about **1–2 heads-up c-bet spots per 100 hands against any one opponent**. A "fold-to-cbet vs X" stat therefore gains only about 1.5 observations per 100 hands.
- **Decay caps the sample.** With half-life H, the effective sample size levels off at about `rate * H / ln2`. With rate = 1.5/100 and H = 300, n_eff is about 6.5. With k = 20 that gives w of about 0.25.
  => **For per-situation postflop stats we are slow and noisy at the same time.** A shorter H makes us noisier, a longer H makes us lag more. An adversary only has to beat one of those two failure modes.
- **Unequal data rates.** Preflop stats (VPIP, open, fold to steal) accumulate about 10–20 times faster than postflop situation stats. An adapter that keys on our preflop tendencies learns us much faster than we learn its postflop tendencies.
- **Opponents can build our stats too.** All public actions and showdowns are observable, so any opponent can compute OUR fold-to-steal, fold-to-3bet, c-bet %, fold-to-check-raise and turn-barrel %. Stacks reset every hand, so nothing hides a pattern behind stack dynamics.

## Common test harness (applies to every scenario)

- Run every scenario twice with duplicate deals and seat rotation, at least 20k hands each: once with **hero model ON** and once with **hero model OFF** (baseline only). The primary metric is `delta = bb100(ON) - bb100(OFF)`, reported per opponent seat and in total.
- A problem is **confirmed** if delta < 0 against the target dummy, or if delta is materially below the "oracle" exploit, meaning hero given the dummy's true parameters.
- Also log, per opponent, the trajectory of hero's model estimate against the dummy's true current parameter. This lag/error curve is the diagnostic.
- Dummies use only the contract: `act(obs)` and `observe(event)`. Helper used in the pseudocode: `strength(hole, board)` returns one of {air, draw, weak_pair, top_pair, two_pair_plus}, built from the arena `evaluator.py`. `pos(seat, button, n)` returns {BTN, CO, SB, BB, EP, MP}.

**Shared dummy component: `SeatStats(window W)`.** One instance per seat, built from `observe` events only. It holds a rolling deque of the last W opportunities per stat:

```
on action events, per seat s, update:
  fold_to_steal_BB[s]   # s in BB, unopened to a late-position (LP) open, s folds?
  fold_to_3bet[s]       # s opened, faced a 3bet, s folds?
  cbet[s]               # s was preflop raiser (PFR), flop checked to s, s bets?
  fold_to_xr[s]         # s c-bet, got check-raised, s folds?
  turn_barrel[s]        # s c-bet, got called, turn checked to s, s bets?
  fold_to_cbet[s], vpip[s], pfr[s]
freq(stat, s) = mean(deque)  if len(deque) >= MIN_N  else None
```

---

## Problems, ranked by expected cost (impact x likelihood)

### 1. `targeted-exploit-dilution`

**Description.** Adaptive bots model every seat, so their behaviour against us depends on OUR stats and differs from their behaviour against everyone else. If our per-situation stats for X pool all of X's opportunities ("X check-raises a c-bet 11%"), behaviour aimed at us is averaged in with X's behaviour against the other 6–7 seats.

The model then reports "X is normal" while X check-raises us 50% of the time, steals 90% when we are in the BB, or 3bets us light. The safety budget does not help: it limits our deviations, and the problem here is that we fail to deviate.

**Why it costs bb/100 (hypothesis).**
- **C-bet line.** X faces our c-bets in about 1.5 spots per 100 hands. If X check-raises us with any two 50% of the time, our range-c-bet loses about 2–3bb per spot instead of winning about 1bb. Cost: roughly 3–5 bb/100.
- **Steal line.** X opens any two from BTN/CO/SB when we are BB and we fold 70% or more. Each steal is worth about +1.5bb to X. Two to three extra steals per 100 hands costs us roughly 1.5–3 bb/100.
- **Dilution.** Our model sees X's pooled LP open rise only from 40% to about 45%, so no defence adjustment fires.

**Test scenario.**

```
Dummy TargetedThresholdBot(W=100, MIN_N=20, T_steal=0.65, T_cbet=0.60, T_xr=0.50):
  stats = SeatStats(W) for every seat
  act(obs):
    me = obs.seat
    # identify the most exploitable seat at this decision
    if preflop and unopened and pos(me) in {CO, BTN, SB}:
        bb_seat = big blind seat
        if freq(fold_to_steal_BB, bb_seat) > T_steal: raise to 2.5bb with ANY two
        else: open standard top-25% range
    if flop and facing a c-bet from seat a and heads-up:
        if freq(cbet, a) > T_cbet and freq(fold_to_xr, a) > T_xr:
             raise to 3x the bet with ANY two                  # targeted check-raise
        else: continue only with top_pair+ or draw; check-raise 5% with two_pair_plus
    otherwise: tight-solid default (top 15% preflop, bet top_pair+, fold air to bets)
Table mix (8): hero, TargetedThresholdBot x2, TightPassive x2, CallingStation x1,
               LAG-static x1, RandomShover(p=0.03) x1
```

Pass criterion: hero's model estimates of "X check-raises vs hero" and "X opens when hero is BB" should converge to the true targeted values (about 0.5 and about 0.9) within about 300 hands. Delta(ON-OFF) should be at least 0 against the targeted bots.

**Estimated impact:** 2–5 bb/100. **Likelihood:** medium-high. Any adaptive bot that keys on per-seat stats produces opponent-specific behaviour by construction, even when it is not deliberately "targeting" us.

**Fix ideas.**
1. Keep **hierarchical "X-vs-hero" stats** alongside the "X-vs-field" stats: `p_vs_hero = (n_h * p_h + k2 * p_x_field) / (n_h + k2)` with a smaller k2, because the field prior is a weak predictor for targeted lines. Add a quick difference test (binomial z on vs-hero against vs-field). If it is significant, drop the field prior for that opponent and situation.
2. Self-check: when any of OUR observable stats crosses a commonly used exploit threshold (see problem 2), assume someone is targeting us and pre-emptively rebalance.

---

### 2. `predictable-self-stats` (we are the one being modelled)

**Description.** Fast learners (window 30–50) and threshold exploiters compute our public stats. A "balanced-ish" baseline built by hand almost always has a few lopsided frequencies at 7–8 handed:
- folding the BB to steals 70% or more
- folding to 3bets 60% or more with a 20% opening range
- c-betting 70% or more and then giving up the turn (turn barrel under 35%)
- folding to check-raises 60% or more

These are cheap to detect because preflop stats accumulate fast. Our exploit layer can make it worse. Once we start exploiting a station (value-heavy, no bluffs) or a nit (bluff-heavy), our aggregate frequencies swing, and a fast learner keyed on our recent window exploits that swing at the rest of the table.

**Why it costs bb/100 (hypothesis).**
- **Fold-to-3bet leak.** A 3bet to 7.5bb against our 2.5bb open wins 4bb (2.5 + 1.5 blinds) when we fold 65% of the time. A rough EV for X is +1.5bb per attempt. With 4–5 attempts per 100 hands from adapters, we lose 4–7 bb/100.
- **Float-and-stab leak.** If we turn-barrel under 35%, X floats the flop c-bet and takes the pot when we check the turn: about +3bb per spot, 1–1.5 spots per 100 hands, roughly 3 bb/100.
- **Combined.** These leaks are not independent of problem 1, but they are real even when we detect the targeting late. Total exposure is plausibly 3–8 bb/100 against 2–3 fast exploiters.

**Test scenario.**

```
Dummy FastSelfStatExploiter(W=40, MIN_N=12,
       T_fold3b=0.60, T_steal=0.65, T_barrel=0.35, T_fxr=0.55):
  stats = SeatStats(W)
  act(obs):
    opener = seat that open-raised this hand (if any, and folded to me)
    if preflop and opener and freq(fold_to_3bet, opener) > T_fold3b:
        3bet to 3x opener's raise with ANY two; if opener 4bets: fold unless QQ+/AK
    if preflop unopened in CO/BTN/SB and freq(fold_to_steal_BB, bb) > T_steal:
        open ANY two to 2.2bb
    if flop, facing a c-bet heads-up from a, in position,
       and freq(turn_barrel, a) < T_barrel:
        call with ANY two (float); on turn if a checks: bet 0.6 pot; if a bets: fold air
    if flop, out of position vs a c-bet and freq(fold_to_xr, a) > T_fxr:
        check-raise ANY two to 3x
    else: tight-solid default
Variant SlowSelfStatExploiter: same rules, W=300, MIN_N=60.
Table mix (7): hero, FastSelfStatExploiter x2, SlowSelfStatExploiter x1,
               CallingStation x1, Nit x1, RandomShover(p=0.03) x1
```

Instrument the run by printing **hero's own public stats**, computed exactly as the dummy computes them, every 100 hands. Pass criterion: none of hero's stats spends more than 20% of the time beyond the threshold, and delta(ON-OFF) is at least 0. Also report hero's bb/100 in the subset of hands where a dummy's rule fired against hero.

**Estimated impact:** 3–8 bb/100. **Likelihood:** medium (needs only one or two adaptive bots, and "if fold% > X then attack" is the most common weekend-built adaptive rule).

**Fix ideas.**
1. **Self-model + MDF floors.** Track our own public stats with the same windows opponents would plausibly use (40, 100, 300). Enforce per-situation floors near minimum defence frequency: BB defend vs a 2.5x steal at least about 40–45%, continue vs 3bet at least about 40% of the opening range, barrel turn at least about 45% of c-bets on favourable cards, continue vs check-raise at least about 35–40%. Choose the defending hands by mixed randomisation, not hard thresholds.
2. **Exploit masking.** When exploiting one seat, keep our aggregate public frequencies inside a band. For example, when we stop bluffing a station, add the "missing" bluffs in spots against folders, so the table-wide stat stays stable.

---

### 3. `stake-asymmetric-poisoning`

**Description.** The model weights every observation equally. An opponent who behaves differently in small and large pots teaches us one stat cheaply and punishes it expensively.

This happens naturally. Rule bots that "call if equity > pot odds" fold more to big bets, and many bots fold limped or tiny pots casually and play "seriously" in raised pots. It can also be deliberate poisoning: fold to every bet when the pot is under 8bb, never fold any pair or draw when the pot is over 15bb. If fold-to-bet is not conditioned on pot size and bet-size bucket, we generalise "X folds 70%" into the expensive pots.

**Why it costs bb/100 (hypothesis).**
- **What it costs X to teach us.** The lesson costs X about 1–2bb per small pot.
- **What it costs us to act on it.** A misplaced big bluff (turn/river barrel in a 20bb or larger pot) costs us 10–20bb. We get about 0.5–1 large contested pots per 100 hands against X.
- **Net.** If 50% of our big-pot bluffs against X are misguided: roughly −3 bb/100, partly offset by the small pots we win. Net estimate: −1 to −4 bb/100 relative to model-off.

**Test scenario.**

```
Dummy StakeAsymmetricBot(SMALL_POT=8bb, BIG_POT=15bb):
  act(obs):
    p = obs.pot / bb
    s = strength(hole, board)
    preflop: open/call top 35%, never 3bet without QQ+
    facing bet postflop:
       if p < SMALL_POT: fold unless s in {top_pair, two_pair_plus}   # ~75% fold, looks "foldy"
       elif p >= BIG_POT: call with any s != air; with air call 40% on flop, 25% turn, 15% river
       else: fold air, call others
    betting: bet 0.75 pot only with two_pair_plus; never bluff
Variant PotOddsBot (natural version): call iff equity_vs_random(hole, board) > bet/(pot+2*bet) + 0.05
Table mix (7): hero, StakeAsymmetricBot x2, PotOddsBot x1, TightPassive x1,
               LAG-static x1, CallingStation x1
```

Measure the model's fold-to-bet estimate for the dummy split into true small-pot and big-pot rates, plus hero's bluff frequency and EV in big pots against the dummy. Pass criterion: hero's big-pot bluff rate against the dummy falls below hero's baseline bluff rate.

**Estimated impact:** 1–4 bb/100. **Likelihood:** high for the natural version (pot-odds and pot-size heuristics are everywhere in student bots), low-medium for deliberate poisoning.

**Fix ideas.**
1. **Condition stats on context buckets**: pot-size bucket (under 8, 8–20, over 20bb) by bet/pot bucket (under 0.4, 0.4–0.8, over 0.8). Use partial pooling, shrinking each bucket toward X's overall rate with a weak prior and toward the field rate for that bucket with a stronger prior. Allow exploitation in a big-pot bucket only on big-pot evidence.
2. **Stake-weighted safety budget.** The allowed exploit deviation in a spot scales with the confidence of the bucket matching that spot's pot size, never the global stat.

---

### 4. `regime-switch-lag` (deceivers and oscillating adapters)

**Description.** A deceiver shows a pattern long enough for us to commit to an exploit, then reverses it, for example folding to c-bets 80% for 150 hands and then never folding. An adapter that defends when it notices our exploit does the same thing reactively. With decay half-life H and the sparse data rates from section 0, our estimate keeps recommending the stale exploit for about 0.5–1 H hands after the switch.

Two weaknesses make this worse:
- The safety budget, if funded by realised winnings (especially table-global), is "refilled" by the deceiver's phase-A gifts or by unrelated run-good. That grants the most deviation exactly when the reversal comes.
- A periodic switcher with period about H makes us exploit the wrong regime most of the time.

**Why it costs bb/100 (hypothesis).**
- **Lag after the switch.** With n_eff of about 6 and estimate 0.8, three new "call" observations move us only to about 0.55–0.6, so we keep bluffing.
- **Phase B cost.** About 2 extra failed c-bet/barrel bluffs per 100 hands at about 4bb each.
- **Net.** The deceiver keeps phase A cheap (combine with problem 3). Net estimate: −1 to −3 bb/100 per deceiver relative to model-off. Against a reactive adapter, our exploit gains are roughly cancelled and we pay for the transitions.

**Test scenario.**

```
Dummy PhaseDeceiver(L_A=150, L_B=100, start_phase=A):
  phase = A if ((hands_seen mod (L_A+L_B)) < L_A) else B
  act(obs):
    s = strength(hole, board)
    preflop: call/open top 30%
    facing postflop bet:
      phase A: fold unless s in {top_pair, two_pair_plus}       # fold-to-cbet ~80%
      phase B: never fold s != air; air: call flop 70%, check-raise 30% on flop
    betting: phase A never bluff; phase B bet 0.6 pot when checked to, any hand, 50%

Dummy ReactiveAdapter(W=30 encounters, T_exploited=0.70, COOLDOWN=80 hands):
  track for each opponent a: cbet_vs_me[a] over last W heads-up flops vs a
  mode[a] = DEFEND if freq(cbet_vs_me[a]) > T_exploited, else FOLDY
  (mode is held at least COOLDOWN hands before re-evaluation)
  FOLDY: fold non-pair to c-bet; DEFEND: call any two flop, raise 25%

Sweep: L_A, L_B in {50, 100, 200, 400}; also set L_A+L_B close to hero's H.
Table mix (7): hero, PhaseDeceiver x1, ReactiveAdapter x1, CallingStation x1,
               Nit x1, TightPassive x1, RandomShover(p=0.03) x1
```

Plot hero's estimate against the true rate over time, the lag in hands from switch to estimate crossing 0.5, and the EV of hero's c-bet bluffs against the dummy split by phase. Pass criterion: lag under about 40 hands, and delta(ON-OFF) of at least −0.5 against the deceiver in the worst case of the sweep.

**Estimated impact:** 1–3 bb/100 per deceiver/adapter (worst when the period is matched to H). **Likelihood:** low for deliberate deceivers, medium for reactive adapters that naturally oscillate.

**Fix ideas.**
1. **Change-point detection plus exploit stop-loss.**
   - Run a per-(opponent, situation) CUSUM or Bayesian online change-point test. On detection, reset that stat's n_eff to a small value, or shrink hard to the prior.
   - Independently, track the realised EV of each active exploit line against each opponent (all-in adjusted). If the last m (about 4–6) applications are net negative beyond about 1 standard deviation, suspend that exploit for that opponent and fall back to the baseline.
   - Contradicting evidence should move us faster than confirming evidence: asymmetric decay.
2. **Per-opponent, EV-denominated safety budget.**
   - Fund the budget only from EV gained against that same opponent (all-in-adjusted, not realised chips), so a gift from station A cannot pay for over-bluffing deceiver B.
   - Add a small random jitter to H and to exploit intensity, so a fixed switching period cannot lock onto us.

---

### 5. `showdown-advertising-poison`

**Description.** Showdowns are the highest-information events, and many models weight them heavily: "bluff ratio at showdown", "shows junk → maniac". An advertiser deliberately reaches showdown with trash in cheap ways early: min-bet river bluffs that get called, a couple of preflop junk shoves. Our "X bluffs a lot" estimate inflates, and we widen our bluff-catching range against X. X then switches to large bets only with two pair or better.

A related natural case: a random-timer shover whose occasional junk shoves get shown, mixed with a value-only big-bet strategy.

**Why it costs bb/100 (hypothesis).**
- **Per bad call.** Each extra bluff-catch against a value-only pot-sized bet loses about 8–15bb.
- **Frequency.** 0.2–0.4 such spots per 100 hands against X gives roughly 2–4 bb/100 gross.
- **Cost to X of advertising.** The ads cost X about 1bb each.
- **Net.** −1 to −3 bb/100 if our showdown evidence is not tied to bet size.

**Test scenario.**

```
Dummy ShowdownAdvertiser(AD_HANDS=80, AD_SHOVES=2, MIN_BET_BLUFF_P=0.5):
  act(obs):
    s = strength(hole, board)
    if hands_seen < AD_HANDS:
        if preflop and ad_shoves_done < AD_SHOVES and hole is junk (e.g. 72o..94o) and unopened:
            raise to max_raise_to (all-in); ad_shoves_done += 1
        if river and checked to me and s == air and rand() < MIN_BET_BLUFF_P:
            raise to min_raise_to (min-bet)        # cheap bluff that often gets called → shown
        else: tight-solid default
    else:
        bets/raises >= 0.75 pot ONLY with two_pair_plus; never bluff; call with top_pair+
Table mix (7): hero, ShowdownAdvertiser x1, RandomShover(p=0.04) x1 (natural version),
               ValueOnlyBigBettor x1, TightPassive x1, CallingStation x1, LAG-static x1
```

Measure the model's "bluff frequency" estimate for X by bet-size bucket, hero's call rate against X's at-least-0.75-pot bets after hand 80, and the EV of those calls. Pass criterion: hero's call rate against X's big bets is no higher than hero's baseline.

**Estimated impact:** 1–3 bb/100. **Likelihood:** low for deliberate advertising, medium for the natural shover/value mix.

**Fix ideas.**
1. **Tie showdown evidence to the action it is evidence for.** A shown min-bet bluff updates only the "small-bet bluff" bucket, and a shown junk shove updates only the "preflop shove range" stat. Big-bet bluff frequency needs big-bet showdowns.
2. **Cap the weight of a single showdown** (count it as one observation, not several), and decay showdown-derived "deception" evidence faster than action stats.

---

### 6. `adaptive-feedback-oscillation` (copycats, mirrors, mutual learners)

**Description.** Copycats (copy hero's frequencies, or copy the style of the winningest seat) and other learners make X's stats a lagged function of OUR behaviour. Our decay model assumes X drifts on its own, so with two coupled lagged learners we get limit cycles. Example:
1. We loosen against a weak table.
2. The mirror loosens.
3. We read X as weak and iso-raise X more.
4. The mirror copies our aggression.
5. We tighten.
6. And so on.

A copy-the-winner bot that copies us while we exploit becomes a second player with our current exploit profile. Our model then exploits a moving reflection of ourselves, and we pay at every transition.

**Why it costs bb/100 (hypothesis).** This mostly destroys our exploit value against these bots rather than producing large losses. Each phase transition costs a few misplayed spots. Estimate 0.5–2 bb/100.

**Test scenario.**

```
Dummy MirrorBot(W=50, LAG_UPDATE=25):
  every LAG_UPDATE hands: target = hero-or-most-profitable seat (by cumulative deltas)
       copy that seat's vpip, pfr, cbet, af over last W hands
  act(obs):
    open/call with top (vpip_copy)% hands, raise with top (pfr_copy)%,
    c-bet with prob cbet_copy, bet/raise postflop with prob scaled by af_copy and strength
Dummy CopyWinner(W=200): same, but target = seat with max cumulative deltas, re-picked each 100 hands
Table mix (8): hero, MirrorBot x2, CopyWinner x1, CallingStation x1, Nit x1,
               TightPassive x1, RandomShover(p=0.03) x1
```

Measure the autocorrelation and oscillation amplitude of hero's VPIP/PFR and of the mirror's stats, and the cross-correlation between hero's lagged stats and X's stats. Pass criterion: no sustained oscillation (amplitude under 5 percentage points) and delta(ON-OFF) of at least 0 against the mirrors.

**Estimated impact:** 0.5–2 bb/100. **Likelihood:** low-medium.

**Fix ideas.**
1. **Damping.** Cap how much our exploit intensity against one opponent can change per 100 hands, and add randomised exploit intensity. Detect "X's stats correlate with our own lagged stats" (correlation over about 0.6), and if so freeze the exploits against X at the baseline.
2. Against copiers, prefer **exploits that stay profitable if mirrored** (e.g. value-heavy lines against stations) over frequency-shift exploits.

---

### 7. `seat-identity-drift` (format-dependent)

**Description.** The model keys opponents by seat index, which is the only identity the contract gives us. Two cases break this:
- The official engine reshuffles seats between hands or matches while our `Agent` instance persists.
- A different bot sits down in a seat between matches.

Either way, stats from two bots merge. Stats stay "confident" but wrong for about H hands, and a deliberately inconsistent opponent looks the same as a seat change. This is a poisoning channel no one has to plan: our own decay keeps the old identity's data alive.

**Why it costs bb/100 (hypothesis).**
- **If reshuffles happen** every R hands with R not much larger than H, the exploit layer acts on the wrong bot about 30–60% of the time, which is worse than model-off.
- **If seats are stable** within a match and the Agent is re-instantiated per match, the impact is zero.

**Test scenario.**

```
Harness variant: keep ONE hero Agent instance; every R hands (R in {50, 200, 1000})
  apply a random permutation to opponent seats (hero informed only via normal obs/events).
Opponents: CallingStation, Nit, LAG-static, TightPassive, RandomShover(p=0.03), PhaseDeceiver
  (strongly distinct styles so mis-attribution is costly).
```

Measure delta(ON-OFF) as a function of R, and the hands it takes after a permutation for the per-seat estimates to recover. Pass criterion: delta(ON-OFF) of at least 0 for every R.

**Estimated impact:** 0 (stable seats) up to 1–3 bb/100 (frequent reshuffles). **Likelihood:** unknown until the official rules are known. Re-check when they are.

**Fix ideas.**
1. **Style-break detector per seat.** If a seat's short-window VPIP/PFR/AF jumps by more than about 3 standard deviations from its long-window profile, or `num_players`/`hand_id` discontinuities appear, reset that seat to the prior. If the official rules expose player IDs, key the model on those.
2. Treat the model's state as **disposable**: cap n_eff so a full relearn takes at most about 150 hands, and never let a stale profile push the deviation past the safety budget.

---

## Field notes (non-problems, hypotheses)

- **Slow learners** (windows of 300 hands or more) are effectively static on our decay timescale. They are good exploit targets, and our main risk against them is problem 2 drifting slowly. Their large windows also mean our MDF self-balancing (fix for problem 2) takes a long time to pay off with them, but it costs nothing.
- **Table-wide adapters** (tighten or loosen according to the table average) mostly react to the stations and maniacs, not to us. The risk is that our model attributes table-driven shifts to "X changed vs us". The vs-hero versus vs-field split (fix for problem 1) also helps here.
- **Cheapest shared mitigation across problems 1, 2, 4 and 5**: per-(opponent, situation, context-bucket) stats with partial pooling, an EV-denominated per-opponent safety budget, an exploit stop-loss, and a self-model with MDF floors. A solver can likely address several problems with one well-designed "trust layer".
