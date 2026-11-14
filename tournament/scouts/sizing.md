# Scout report: unusual bet sizes (offense and defense)

Scout angle: tiny bets, min-raises, odd overbets and odd chip counts, from both sides.
Status: **every strategy claim here is a hypothesis.** Nothing has been run in the arena. Note that this
clone has no `tournament/arena/` yet, so the dummy bots below are specs for `arena/bots/`, not existing code.
The claim that odd sizes reliably exploit competition bots is **unverified**. The EV numbers are rough
back-of-envelope estimates meant for ranking, not predictions.

## Shared definitions (pseudocode, against the candidate contract)

```
# Price of a call, valid for any number of players:
req_equity(obs)  = obs.to_call / (obs.pot + obs.to_call)      # obs.pot already includes this street's bets

# Bet size as a fraction of the pot before the bet (heads-up single bet; approximate when multiway):
bet_frac(obs)    = obs.to_call / max(1, obs.pot - obs.to_call)

# MDF against a single bet of fraction f is 1/(1+f). Break-even fold rate for a pure bluff of f is f/(1+f).

# "Raise to" helper: puts in frac * (pot after our call) on top of the current high bet.
def size_to(obs, frac):
    my   = obs.bets[obs.seat]
    cur  = my + obs.to_call                    # current high bet this street
    tgt  = cur + frac * (obs.pot + obs.to_call)
    amt  = int(round(tgt))
    return clamp(amt, obs.min_raise_to, obs.max_raise_to)   # max_raise_to = all-in; may be < "full" min raise

def safe_raise(obs, amt):
    if 'raise' not in obs.legal: return call_or_check(obs)
    return {'action':'raise', 'amount': clamp(int(amt), obs.min_raise_to, obs.max_raise_to)}

# Rules recap (from CONTEXT.md plus standard NLHE; confirm against official rules later):
#  - min raise-to = current high bet + last full raise increment. Preflop: BB=20, so min open = 40.
#    After an open to 60 (increment 40), min 3-bet = 100. Postflop the first bet is >= BB (20).
#  - An all-in may be less than a min raise. Under standard rules an incomplete raise does NOT reopen
#    betting for players who already acted (this is engine-dependent, so test it).
```

**Key observation about the field (hypothesis, but a cheap one):** for a weekend bot author, the
two easiest legal raise amounts are `obs['min_raise_to']` and `obs['max_raise_to']`. So we expect the field's
sizing to be **bimodal: min-raises and all-ins**, with few "normal" 50–75% pot bets. Defense should be tuned for
both extremes first. Offense should target opponents whose continue decision ignores size, since that
is the most common weekend design: a hand-strength threshold with no pot-odds term.

**Common diagnostic: fold-curve probe** (used by several tests below). A dummy bot `SizeSweeper` bets a
fraction f drawn from {0.05, 0.1, 0.2, 0.33, 0.49, 0.51, 0.66, 0.74, 0.76, 0.99, 1.01, 1.5, 1.7, 2, 3, 5, jam}
with **random hole cards**, at a fixed frequency. Log the candidate's (f, street, action, hand equity vs random).
Plot the candidate's fold frequency against f and compare it with MDF = 1/(1+f). Flag (a) jumps of more than 10
percentage points between adjacent sizes (a bucket boundary) and (b) fold frequency above MDF by more than 15
percentage points at any size (overfolding to a random-hand bettor).

---

## Ranked problems

### 1. `value-size-inelastic-callers` (offense)

**Description.** Calling stations and threshold bots ("call with any pair or draw") decide whether to continue
from their hand class, not from the price. Against such an opponent, the EV of a value bet rises almost linearly
with its size, so a candidate that uses fixed value sizes (2/3 pot postflop, 2.5–3x preflop) leaves most of the
money behind. Odd overbets (1.5x, 1.7x, 3x pot) and big preflop opens (4–5x, or 5x plus 1x per limper) are the
fix for those opponents only.

**Why it costs bb/100 (rough).** River, pot 300 (15bb), we hold two pair or better, and the station calls with any
pair (call probability c of about 0.6) whatever the size. Betting 600 (2x) instead of 200 (2/3) adds 400 chips
when called. Gain is about c x (0.9*400 - 0.1*400) = 0.6 x 320 = 192 chips, or about 9.6bb per spot. With 1–2
such spots per 100 hands at a table with 2 stations, that is about +10–20 bb/100 from the river alone. Turn and
flop sizing on a geometric plan compounds it. Preflop: opening premiums to 100 instead of 60 against stations who
call any size adds 40 chips x (number of callers) per open.

**Test scenario.**
```
Table (7 seats): candidate, Station x2, ThresholdCaller x2, TightPassive x1, BaselineIncumbent x1

Station.act(obs):
    if obs.to_call == 0: return check (or bet size_to(obs,0.5) with two-pair+ at 30%)
    if hand_class >= PAIR or has_draw(8+ outs) or obs.street=='preflop': return call
    return fold if req_equity(obs) > 0.25 else call          # calls almost everything; ignores size

ThresholdCaller.act(obs):                                     # size-blind threshold bot
    preflop: call any raise with top 40% of hands, else fold; never raise
    postflop: if to_call > 0: call iff hand_class >= PAIR (any size, up to all-in) else fold
              else check

Metric: candidate bb/100 split by (opponent type in the pot), plus chips won per showdown in pots with a
station. Compare against an A/B copy of the candidate whose value sizes are scaled by 2.0 (capped at all-in)
and preflop opens of 5bb when a station is yet to act.
```
**Estimated impact:** +5 to +15 bb/100 if 2 or more size-inelastic bots are present. **Likelihood:** high (the field
list names calling stations).

**Fix ideas.**
1. Track per-opponent **size elasticity**: call rate against bets bucketed into small (f<0.4), medium, and large (f>1),
   for example as a Beta posterior per bucket. When large-bet call rate is at least 0.8x small-bet call rate over
   n of 15 or more, mark the opponent inelastic and scale value sizing up to 1.0–2.0x pot (river: jam if
   stack-to-pot ratio is 3 or less). Bluff zero against that opponent.
2. Use the size of the pot at the start of the hand when a station is in it: open to 5bb plus 1bb per limper with
   value hands, and use a geometric plan aimed at stacks in by the river with two-pair+ hands.

---

### 2. `bimodal-field-min-raise-war` (defense)

**Description.** Min-raises (raise to `min_raise_to`) are likely the most common non-all-in raise in the field.
Two baseline failure modes:
(a) **Overfold.** A baseline that reads "facing any raise" as strength (for example "continue only with the top
X% when raised") gives up its open to a 1-increment re-raise from a random or near-random bot.
(b) **Escalation.** A baseline that decides each step from incremental pot odds (each min-raise only offers
17–25%) calls one step at a time and ends up in a 40–80bb pot with a medium hand. A baseline that re-raises by
a multiple of the *increment* instead of the pot (for example "raise to cur + 2*last_increment") enters a slow
raise spiral that ends all-in with ranges it never meant to stack off.

**Why it costs bb/100 (rough).** Preflop: we open to 60, and the MinRaiser re-raises to 100. Its break-even fold
rate is 100/(100+90) = 53%. If the baseline folds about 70% of its opening range, MinRaiser profits about 0.17
x 90 = 15 chips per attempt plus equity. At the same time, the price we are offered is 40/230 = 17%, so folding
anything is close to a gift. Postflop min-raise wars (bet 20, raise 40, raise 60, ...) are slow but drain chips in
large multiway pots. Estimated -2 to -6 bb/100 when one or two lazy min-raisers sit at the table. Escalation adds
variance and roughly -1 to -3 bb/100 when the min-raiser is actually value-heavy (a deceptive bot).

**Test scenario.**
```
Table (7 seats): candidate, MinRaiserRandom x2, MinRaiserValue x1, Station x1, TightPassive x2

MinRaiserRandom.act(obs):                                   # lazy author: always min, random hands
    raises_this_street = count(history where street==obs.street and action=='raise' and seat==me)
    if 'raise' in obs.legal and raises_this_street < 4 and rng() < 0.6:
        return {'action':'raise','amount': obs.min_raise_to}
    return call if 'call' in obs.legal and rng() < 0.7 else check_or_fold

MinRaiserValue.act(obs):                                    # same sizes, real hands
    strength = equity_vs_random(hole, board, iters=200)
    if strength > 0.70 and 'raise' in obs.legal: return {'action':'raise','amount': obs.min_raise_to}   # no cap
    if strength > 0.45: return call_or_check
    return check_or_fold

Metrics: (1) candidate fold frequency when facing a min-raise, by street, compared with 1 - req_equity;
(2) the distribution of final pot size when candidate shows down against MinRaiserValue with a hand of
equity < 0.6; (3) number of raises per street (detects spirals); (4) bb/100 split by opponent.
Also check decision count per hand and act() latency (a war to all-in at a 20-chip increment can take ~50 actions).
```
**Estimated impact:** -2 to -6 bb/100. **Likelihood:** high (`min_raise_to` is the easiest raise to code).

**Fix ideas.**
1. Decide facing a raise by **total price plus opponent model**, not by "was raised": continue range =
   equity vs opponent's estimated raise range (wide if their raise frequency is above 25%) > req_equity, with a
   realization discount out of position. Against a raise-frequent min-raiser, 3-bet or jam a polarized value range
   (pot-sized, not increment-sized) and call the rest.
2. Use a **street commitment plan**: before calling a raise, project the pot if it goes N more increments; if
   the hand cannot stand a stack-to-pot ratio below 1, either jam now (with strong hands) or fold at a fixed
   cap (for example no more than 3 calls of raises per street with less than top pair). Re-raise sizes are always
   pot-based: `size_to(obs, 0.8..1.0)`.

---

### 3. `size-blind-folders-tiny-stabs` (offense)

**Description.** Threshold bots that fold every unpaired hand to *any* bet (ThresholdFolder, TightPassive) give
the same fold equity to a 10–25% pot bet as to a pot-sized one. Tiny stabs need only 9–20% folds to break even
(f/(1+f)), so with air they cost less than standard c-bets and gain the same amount. Min-bets (20 chips) into
large pots are the extreme case: break-even fold rate is 20/(P+20).

**Why it costs bb/100 (rough).** Heads-up versus a folder who misses about 65% of flops and folds all misses:
profit at 25% pot is about 0.65P - 0.35 x 0.25P x 0.8 = 0.58P; at 66% pot it is about 0.46P. The difference
is about 0.12P, roughly 0.7bb in a 6bb pot. That gives **+1 to +4 bb/100 incremental** over a baseline that already
c-bets 2/3, and more if the baseline does not stab at all. Multiway: fold equity multiplies, and the fold rates
of non-folders (stations) are near 0, so only stab when every live opponent is a folder type, or when there are
at most 2 opponents. Downside: tiny bets are called or raised wider by price-aware bots (pot-odds bots call 25%
pot with 17% equity, so almost anything), so the size must be per-opponent.

**Test scenario.**
```
Table (7 seats): candidate, ThresholdFolder x2, TightPassive x2, PotOddsNaive x1, Station x1

ThresholdFolder.act(obs):
    preflop: call raises up to 4bb with top 35%, fold rest; check BB option
    postflop facing bet (any size, including 20 chips): continue iff hand_class >= PAIR or flush draw; else fold
    postflop no bet: check (bet size_to(obs,0.66) with two pair+)

PotOddsNaive.act(obs):                                     # price-aware, range-unaware
    e = equity_vs_random(hole, board, iters=300)
    if obs.to_call == 0: bet size_to(obs,0.6) if e > 0.75 else check
    return call if e > req_equity(obs) else fold

Metric: candidate EV per postflop "checked-to, no made hand" spot, split by which opponents are in the
pot. A/B: candidate stabbing size 0.25 vs 0.66 vs 0.10, only when all live opponents are flagged folders.
Expected (hypothesis): 0.25 > 0.66 against folders; 0.25 < 0 against PotOddsNaive and Station.
```
**Estimated impact:** +1 to +4 bb/100 incremental. **Likelihood:** medium-high (threshold logic is common;
whether the folders actually ignore size is the unverified part).

**Fix ideas.**
1. Per-opponent **fold-to-bet by size bucket** (small/medium/large) with a prior that bots are size-blind. Choose
   the stab size that maximizes `P(all fold | size) * pot - (1 - P(all fold)) * size * (1 - realization)`
   over the sizes {0.1, 0.25, 0.5, 0.75}.
2. A simple rule fallback: heads-up or 3-way with no station-flagged opponent left in the pot, checked to us, air
   or weak showdown value means stab 25% pot once; give up on later streets unless the opponent folds to the
   second barrel more than 60% of the time.

---

### 4. `bucket-price-mismap` (defense)

**Description.** A baseline that maps the opponent's bet to a few representative sizes (for example small=0.33,
medium=0.75, large=1.0, all-in) and looks up a required strength per bucket uses the *representative* price, not
the real one.
- **Overbets mapped to "large = 1x"** require 33% equity, but 3x pot really needs 3/7 = 43%, and 5x needs 45%.
  The baseline calls too wide against big value overbets (stations and value bots that jam strong hands).
- **Bets just over a boundary** (0.51 when the small/medium boundary is 0.5) get the tighter bucket's range, and
  **bets just under** get the looser one. The response function is discontinuous, so a varied-size opponent
  (or an adaptive one) can bluff at 0.51 and value bet at 0.49.
- **Tiny bets mapped to "small = 0.33"** require 20% equity instead of 9% (for 10% pot), so the baseline overfolds
  to min-bets (a modest leak, but min-bets may be frequent here).

**Why it costs bb/100 (rough).** Calling a 3x pot overbet with 35% equity: EV = 0.35 x 7P - 3P = -0.55P per call,
or about -8bb in a 15bb pot. Even 1 such call per 100 hands is -5 to -8 bb/100. Overfolding to 10% pot min-bets
gives up about 0.1P per instance (small, but frequent). Boundary exploitation needs an adaptive opponent:
low likelihood.

**Test scenario.**
```
Table (8 seats): candidate, SizeSweeper x1, ValueOverbettor x2, MinBettor x2, Station x1, TightPassive x1

SizeSweeper.act(obs):                                       # random hands, fold-curve probe (see top)
    if obs.street != 'preflop' and obs.to_call == 0 and rng() < 0.5:
        f = rng.choice([0.05,0.1,0.2,0.33,0.49,0.51,0.66,0.74,0.76,0.99,1.01,1.5,1.7,2,3,5])
        return safe_raise(obs, size_to_frac_of_pot_before(obs, f))
    return call if req_equity(obs) < 0.2 else check_or_fold

ValueOverbettor.act(obs):                                   # only overbets with strong hands
    e = equity_vs_random(hole, board, 300)
    if obs.to_call == 0 and e > 0.80: return safe_raise(obs, size_to(obs, rng.choice([1.7, 3.0])))
    if obs.to_call > 0 and e > 0.85: return safe_raise(obs, obs.max_raise_to)
    return call if e > req_equity(obs) else check_or_fold

MinBettor.act(obs):                                         # bets 20 chips every chance, random hand
    if obs.to_call == 0 and 'raise' in obs.legal: return {'action':'raise','amount': obs.min_raise_to}
    return call if hand_class >= PAIR else fold

Metrics: (1) fold-curve discontinuities (adjacent sizes differing by more than 10 points);
(2) candidate's call EV against ValueOverbettor by size (should be close to 0 or positive: fold most);
(3) candidate fold frequency against MinBettor compared with 1/(1+f) = about 0.9 continue.
```
**Estimated impact:** -1 to -6 bb/100 (mostly from overbet overcalls). **Likelihood:** medium (depends on
whether our baseline buckets sizes; if it already uses `req_equity` continuously, this mostly disappears).

**Fix ideas.**
1. Never use representative sizes for *price*. Always compute `req_equity(obs)` from the real to_call and pot.
   Use buckets only to *index the opponent model* (what range bets this size), and interpolate between
   neighbouring buckets (weighted by distance in log f) so the response is continuous in f.
2. Model range by size: for each opponent, keep showdown-revealed strength per size bucket. Default prior: f>1.2
   from a non-shover is value-heavy (polarized, with few bluffs in this field), so tighten calls against
   overbets beyond the pure pot-odds price unless the opponent has shown overbet bluffs.

---

### 5. `raise-to-legality-odd-amounts` (defense / robustness)

**Description.** Sizing code is where illegal actions come from, and an illegal action is auto-folded or
auto-checked (which can fold the nuts). Failure cases:
- Returning a "raise by" amount (`to_call + x`) instead of "raise to" (`cur + x`), so the raise is too small and
  either illegal or a mis-sized min-raise.
- Computing the min-raise from history instead of reading `obs['min_raise_to']`, which is wrong after an
  incomplete all-in. Under standard rules an incomplete all-in does not change the increment and does not
  reopen action for players who already acted, so `'raise'` may be absent from `legal`.
- `min_raise_to > max_raise_to` (only a short all-in is possible). Not clamping to `max_raise_to` makes the
  raise illegal.
- Floats or numpy ints as `amount`; amounts that are not multiples of 10 if our own code asserts that they are;
  a raise when `to_call >= stack` (only call/all-in is possible).
- Parsing opponents' odd amounts in `observe` (for example `amount` = 1999, or 41) in a model that assumes
  multiples of the big blind, then dividing by zero or indexing a bucket out of range.

**Why it costs bb/100 (rough).** One auto-fold of a strong hand in a 30bb pot is -30bb. At 1 failure per 500
hands that is -6 bb/100. The robustness gate may also disqualify a candidate outright.

**Test scenario.**
```
Table (8 seats): candidate, NearJammer x2, OddChip x2, AllInBot x1, MinRaiserRandom x1, Station x1

NearJammer.act(obs):                                         # creates incomplete-raise situations
    if 'raise' in obs.legal and rng() < 0.3:
        return {'action':'raise','amount': max(obs.min_raise_to, obs.max_raise_to - rng.choice([1,7,30,55]))}
    return call_or_check
    # Then AllInBot shoves over it for less than a full raise -> candidate faces an incomplete raise and
    # must handle 'raise' not in legal, or min_raise_to == max_raise_to.

OddChip.act(obs):                                            # odd totals within legal range
    if 'raise' in obs.legal and rng() < 0.4:
        base = size_to(obs, rng.choice([0.1, 0.5, 1.7, 3.0]))
        return {'action':'raise','amount': clamp(base + rng.choice([-3,-1,1,3,7]), obs.min_raise_to, obs.max_raise_to)}
    return call_or_check

AllInBot.act(obs): return raise to obs.max_raise_to if 'raise' in obs.legal else call

Pass criteria: zero illegal actions and zero exceptions over 20k hands; act() p99 below 50 ms; with a fuzzed
harness, every returned amount is an int in [min_raise_to, max_raise_to] and 'raise' only appears when legal.
Also a unit fuzz: random obs dicts with min_raise_to > max_raise_to, to_call > stack, legal=['fold','call'].
```
**Estimated impact:** -1 to -6 bb/100 (heavy tail: possible disqualification). **Likelihood:** medium for new code.

**Fix ideas.**
1. One choke-point function `finalize(obs, intent)` that every decision passes through: maps intent
   (fold/check/call/raise to X) to the legal list, casts to `int`, clamps to [min_raise_to, max_raise_to],
   turns raise into call when 'raise' is absent, turns fold into check when to_call == 0, and wraps act() in
   try/except that falls back to check/call/fold.
2. Opponent models index sizes by `bet_frac` in log-space buckets with clamping. Never assume multiples of BB.

---

### 6. `overbet-bluff-overfold` (defense)

**Description.** The mirror of problem 4. A baseline with a "big bet = strong" heuristic, or thresholds on
absolute hand class against large sizes, folds far above MDF against bots that overbet or jam with random or
semi-random hands (random-timer shovers, deceptive bots, "aggressive" bots that pot or overbet whenever checked
to). Against a 2x pot bet, MDF is 33%. A baseline that folds 85% of its range there lets any-two-cards overbets
print money.

**Why it costs bb/100 (rough).** A bluffer betting 2P into P needs 67% folds. If we fold 85%, each attempt wins
about 0.85P - 0.15 x 2P x (1 - bluffer's equity ~0.3) = 0.64P. In a 10bb pot that is about 6.4bb per attempt. The
bluffer spreads its attempts over 6–7 opponents, and we are only in some of those pots (roughly 0.2–0.6 attempts
against us per 100 hands per bluffer). That puts the realistic cost at -1 to -4 bb/100 for our seat.

**Test scenario.**
```
Table (7 seats): candidate, OverbetBluffer x2, TightPassive x2, Station x1, BaselineIncumbent x1

OverbetBluffer.act(obs):
    if obs.street != 'preflop' and obs.to_call == 0 and 'raise' in obs.legal and rng() < 0.5:   # hand-independent
        return safe_raise(obs, size_to(obs, rng.choice([1.5, 1.7, 2.0, 3.0])))
    if obs.to_call > 0: return call if hand_class >= PAIR else fold
    preflop: limp/call up to 3bb with top 60%

Metrics: candidate fold frequency against OverbetBluffer bets compared with MDF (0.29–0.40 continue);
candidate EV in those pots; check that the candidate does NOT also loosen against ValueOverbettor (from
problem 4). It must separate the two by observed showdown strength per size.
```
**Estimated impact:** -1 to -4 bb/100. **Likelihood:** medium-low (random overbets are less likely than random
all-ins, which another scout probably covers).

**Fix ideas.**
1. Per-opponent **aggression frequency at size**: if an opponent bets more than 1.2x pot in more than 25% of
   checked-to spots, its range there is wide, so call with hands whose equity vs a wide range beats req_equity.
   Default (unknown opponent) remains tight against overbets (see problem 4).
2. Bluff-catch with blockers and showdown-value hands first; raise-jam over overbettors with strong hands
   (they often fold or call badly).

---

### 7. `odd-chip-classifier-breakers` (offense, speculative)

**Description.** Some opponent bots may classify our actions by exact amounts (`to_call == 2*bb` means
"min-raise", `amount % bb == 0`, "open = 3bb" lookup tables, dict keys keyed on exact sizes, integer division
causing 0-sized buckets), or crash on unexpected amounts. Their engine fallback then folds or checks for them.
Odd totals like 41 instead of 40, 63 instead of 60, 1999 instead of a jam, or a 1.7x pot bet can push them onto a
default branch (often fold) or an exception. Allowed per CONTEXT rules (exploiting opponent bots' handling of
unusual inputs), as long as we do not touch the engine. Secondary benefit: ±1–3 chip jitter costs nothing in EV
and defeats exact-amount fingerprinting by adaptive bots ("they always open to 60 with AA").

**Why it costs or gains bb/100 (rough).** Pure upside with near-zero cost: if even one opponent mis-buckets odd
amounts, that is a few extra folds per 100 hands (+0.5 to +2 bb/100). If none do, about 0 is lost.
Jamming 1999 instead of 2000 leaves 1 chip behind: only do this where the 1 chip cannot matter
(hypothesis: it can matter if it changes all-in flags that opponents key on, which may help or hurt).

**Test scenario.**
```
Table (7 seats): candidate_with_jitter, ExactAmountBot x2, ThresholdFolder x2, Station x1, BaselineIncumbent x1

ExactAmountBot.act(obs):                                     # models a brittle opponent
    raise_to = max(obs.bets)
    table = {40:'minraise', 60:'open', 80:'big_open', obs.max_raise_to:'jam'}   # exact keys
    kind  = table.get(raise_to, None)
    if kind is None:  return fold                            # unknown-size branch (or raise KeyError -> engine fold)
    if kind == 'jam': return call if top10(hole) else fold
    return call if top30(hole) else fold

Candidate A/B: identical except candidate_with_jitter adds rng.choice([-3,-2,-1,1,2,3]) to every non-all-in
raise total (still clamped to legal). Metric: bb/100 difference and fold rate of ExactAmountBot.
Expected under the hypothesis: large gain against ExactAmountBot and no difference against the others.
The real-field value is unknown.
```
**Estimated impact:** 0 to +2 bb/100. **Likelihood:** low (unverified that any real bot is this brittle).

**Fix ideas.**
1. Add ±1–3 chip jitter to non-all-in raise totals (seeded by `rng_seed`), clamped to legal. It is free.
2. Prefer non-round fractions for value overbets (1.7x rather than 2x) and opens (2.6bb = 52 rather than 60)
   only if arena tests show no loss. Never jam for 1 chip less unless a test shows a gain.

---

## Which offensive sizes are worth it in a 7–8 player, 100bb field (hypotheses)

| Size | Use against | Avoid against | Verdict |
|---|---|---|---|
| Min-bet / 10% pot | Size-blind folders heads-up; cheap blocker bet on river out of position against bots that bet big when checked to | Pot-odds bots, stations, multiway pots | Niche; per-opponent only |
| 25–33% pot stab | Folders and tight-passive bots, 1–2 opponents | 3 or more opponents with any station | Worth testing (problem 3) |
| Min-raise (preflop or postflop) | Almost never for us: invites multiway calls from stations at a good price | Stations, 8-handed preflop | Avoid; open bigger |
| 1.5–3x pot overbet | Value against size-inelastic callers (stations, pair-threshold callers) | Price-aware or tight bots (they fold worse hands); bluffing multiway | Big value lever (problem 1) |
| Big preflop open (4–5bb + limpers) | Tables with stations or limpers | Tight tables (just steals blinds; 2.5bb is enough) | Adjust by table makeup |
| Odd-chip jitter | Everyone (free) | Nobody | Cheap to add (problem 7) |

## Suggested test order for solvers
1. Robustness fuzz (problem 5) first, since it gates everything else.
2. Fold-curve probe with SizeSweeper on the incumbent (diagnoses problems 4 and 6 at once).
3. Min-raise war table (problem 2), then the station value-sizing A/B (problem 1), then tiny stabs (problem 3).
4. Odd-chip jitter A/B last (problem 7).
