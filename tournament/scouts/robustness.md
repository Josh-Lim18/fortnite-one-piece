# Scout report: robustness and rule edge cases

Angle: the ways a bot crashes, times out, acts illegally, or plays wrong without any error, plus the
engine rules our local arena has to get right so these bugs actually show up in testing.
Everything here is a hypothesis until the arena confirms it. Pseudocode only.

Context checked: `tournament/CONTEXT.md` (contract, rules). No arena code, incumbent bot or talk
notes are in the clone yet, so the "five betting rounds" item is based on the summary in the task
brief and still needs checking against the official rules when they come out.

One measured data point (throwaway benchmark in /tmp, not in the repo): a naive pure-Python
7-card evaluator (best of 21 five-card combos) costs about **0.17 ms per Monte Carlo trial against
1 opponent and 0.43–0.7 ms per trial against 7 opponents** on this container. That gives
**≤ ~100 trials in a 50 ms budget at a full 8-handed table.**

Why robustness is worth bb/100: a failed action is turned into fold/check by the engine. Being
folded by mistake while holding a strong hand in a big pot loses the whole pot, which can be
50–100 bb. One such event per 1,000 hands costs about 5–10 bb/100, which is more than most
strategy edges. Repeated failures may also get us disqualified by the robustness gate.

---

## Ranked problems

### 1. `illegal-action-construction`
**Description.** The action dict is invalid for the current state:
- `raise` when `'raise'` is not in `legal`. This happens after an incomplete all-in that does not
  reopen betting, when `stack <= to_call`, or when every other live player is all-in.
- `amount < min_raise_to` or `amount > max_raise_to`.
- `amount` given as raise-BY (`to_call + x`, or `pot * 0.75`) when the engine expects raise-TO.
- `amount` is a float, a `numpy.int64` or `numpy.float64`, or NaN after division by zero
  (`pot/0` or `equity/0`).
- `check` when `to_call > 0`.
- `call` when `to_call == 0`, which a strict engine may reject.
- Missing `'amount'`, or a key typo such as `'Raise'`.

**Cost.** Each one counts as a robustness failure, and the engine then folds or checks for us.
A failed "raise" that becomes a fold with a monster is the worst case. Raise-by vs raise-to
confusion silently over-bets or under-bets by up to the current bet on every raise, even when the
engine clamps instead of rejecting.

**Test scenario.**
```
fixed obs A (short all-in, raise closed):
  preflop, 8 players. Hero UTG raised to 60. Folds to BTN, who raises to 1200.
  SB shoves 2000 total (increment 800 < last full raise 1140, so it is incomplete).
  Folds back to hero. Expect legal == ['fold','call'], to_call == 1940.
  assert agent.act(obs)['action'] in ('fold','call')
fixed obs B: stack == to_call  -> 'raise' not legal, max_raise_to == current bet
fixed obs C: to_call == 0, legal == ['check','raise']  -> never 'fold', never 'call'
fixed obs D: min_raise_to == max_raise_to (all-in is the only raise size)
fuzz: for 100k random legal states produced by the engine:
  a = agent.act(obs)
  assert type(a['amount']) is int if a['action']=='raise'
  assert a['action'] in obs['legal']
  assert min_raise_to <= a['amount'] <= max_raise_to when raising
  assert not (a['action']=='fold' and 'check' in obs['legal'])   # free-fold leak
```
**Impact high, likelihood high.**

**Fixes.**
1. Send every action through one `sanitize(action, obs)` function just before returning. It
   checks the action against `legal` and, if needed, maps raise to call, call to check, or check
   to fold. It clamps the amount into `[min_raise_to, max_raise_to]` and converts with
   `int(round(x))`. If the target is at or above about 0.9 × `max_raise_to`, it snaps to
   `max_raise_to`.
2. Always compute sizes as raise-TO: `target = bets[seat] + to_call + desired_increment`. Read
   `min_raise_to` and `max_raise_to` from `obs`; never recompute them from history.

### 2. `unhandled-exception-in-act-or-observe`
**Description.** The opponent model or a feature extractor raises an exception on an event it has
not seen before:
- `showdown.hands` / `winners` keys arriving as `str` instead of `int`. Any JSON transport turns
  int keys into strings.
- `action` values the bot does not expect: `'bet'`, `'all_in'`, `'post_sb'`, `'post_bb'`,
  `'timeout'`, or a forced `'fold'` on another bot's failure.
- `amount: None` on check or fold.
- A `board` event with `street == 'showdown'`.
- `observe` never called at all (the contract says it is optional).
- An `action` event arriving before `hand_start`.
- Division by zero in a VPIP or aggression stat for a seat with 0 hands.
- `history` holding the blind posts as action events.
- Index errors on `stacks[seat]` when `num_players` is 7 while the bot assumed 8.

**Cost.** An exception in `act` is a failure plus a forced fold or check. An exception in `observe`
may kill the process or be swallowed by the engine, and if swallowed it can leave the model in a
half-updated, corrupt state that degrades every later decision without any visible error.

**Test scenario.** Use a dummy-bot fuzz spec, the "chaos table":
```
for each event the engine would emit, also emit mutated variants:
  - int keys -> str keys; amount -> None/0/float; unknown action names; extra/missing fields
  - drop hand_start for random hands; duplicate hand_end; observe() never called for whole runs
  - num_players in {2,3,6,7,8}; seat at index 0 and n-1
run 20k hands; assert zero exceptions escape act()/observe(); assert act() still sanitised-legal
```
**Impact high, likelihood high.**

**Fixes.**
1. Wrap the bodies of `act` and `observe` in `try/except Exception`. On error, `act` returns a
   safe fallback (check if legal, otherwise a call/fold rule based only on hand strength) and
   `observe` drops the event. Count the swallowed errors in a counter so local runs can see them.
2. Normalise every event at entry: `seat = int(seat)`, `amount = int(amount or 0)`, and map
   unknown action names to `{bet → raise, all_in → raise or call depending on amount,
   post_* → ignore}`.

### 3. `monte-carlo-time-budget`
**Description.** Monte Carlo equity against all 7 opponents with a fixed trial count. Using the
benchmark above, 1,000 trials is about 430–700 ms per decision in pure Python. The cost depends
on the number of opponents and on the street; preflop is worst because 5 board cards plus 14
hole cards must be dealt. The competition hardware may be slower than ours. Building lookup
tables lazily on the first `act` call also pushes that first decision over budget.

**Cost.** Timeouts are failures plus forced folds. If the engine instead waits, the official
harness may treat it as a timeout or disqualify the bot. Cutting the trial count to stay in budget
makes the equity estimate noisy: with 100 trials the standard error is about ±5%. That causes
thin call/fold mistakes at the margin.

**Test scenario.**
```
for opp in 1..7, street in all, 1000 random obs each:
  t = perf_counter(); agent.act(obs); dt = perf_counter() - t
  record p50/p99/max per (opp, street); FAIL if p99 > 0.5 * budget or max > budget
also: measure the first act() after __init__ separately (cold start)
also: run the same test with CPU throttled (e.g. taskset to 1 core plus a busy sibling process)
```
**Impact high, likelihood medium.** It only bites bots that use Monte Carlo, but they are the ones
most likely to use it naively.

**Fixes.**
1. Run trials against a deadline (`while perf_counter() < t0 + 0.6*budget`) instead of a fixed
   count. Precompute the 169 preflop equities vs 1–7 random hands as a constant table embedded in
   the file, so preflop never runs Monte Carlo.
2. Model only the opponents likely to continue (the remaining aggressors or callers, capped at 2–3)
   and use their ranges instead of random hands. Vectorise the evaluator with numpy (rank and suit
   histograms over a batch of trials). Build all tables in `__init__`.

### 4. `per-hand-state-leak-and-memory-growth`
**Description.** Per-hand variables are reset only on `hand_start`. These include "I was the
preflop aggressor", the number of raises this street, cached equity and the bot's own previous
action. If `observe` is not called, events arrive out of order, or a hand ends early (everyone
folds preflop, so no board events), the old values carry into the next hand. Separately, the full
event history is stored in a list for every hand, and per-opponent dictionaries are keyed by
something unbounded such as `(hand_id, seat)` or a raw history tuple. Over 10k+ hands the memory
use grows and the per-decision scans get slower.

**Cost.** A bot playing the new hand as if it were the preflop aggressor c-bets air every time.
Stale `to_call` assumptions can also feed an illegal action into problem 1. The slowdown from
growing memory eventually turns into timeouts (problem 3).

**Test scenario.**
```
run A: 5k hands with observe() calls enabled; run B: identical seeds, observe() never called.
assert decisions in hand k depend only on obs + model stats (diff A vs B decisions on hands
  where model stats are irrelevant, e.g. first decision of hand -> must be identical)
fixed: hand 1 hero raises preflop, all fold. Hand 2 hero in BB checks to flop.
  assert not state.was_aggressor
memory: tracemalloc snapshot at hand 1k and 20k; FAIL if growth > ~5 MB or act() p99 grows > 20%
```
**Impact medium, likelihood high.**

**Fixes.**
1. Key the reset on `obs['hand_id'] != self.cur_hand`, checked at the top of `act`. Rebuild the
   per-hand facts from `obs['history']`, which is authoritative, instead of from accumulated
   events.
2. Keep opponent statistics as bounded running counters (or `deque(maxlen=N)`) per seat, and
   never store full histories.

### 5. `seat-vs-position-and-button-order`
**Description.** The bot confuses absolute seat index with position relative to the button.
Specific mistakes:
- Hard-coding 8 players in position charts.
- Forgetting that heads-up the button posts the SB, acts first preflop and last postflop.
- With 3+ players, mixing up whether SB or UTG acts first preflop.
- Using the BB's seat to infer "last to act" after folds.
- Counting folded or all-in players as "players left to act".
- Assuming `num_players` equals the number of live seats.
- Off-by-one on `(seat - button) % n` when tables are 7-handed.

**Cost.** This is a silent strategy error. A bot that thinks it is on the button while it is UTG
opens far too wide. Treating all-in players as "to act" makes it fear re-raises that cannot come;
treating them as gone underestimates the number of opponents in equity. Each of these leaks
compounds across most hands.

**Test scenario.**
```
for n in {2,3,7,8}, for button in 0..n-1, for hero seat in 0..n-1:
  pos = agent.position(obs)    # or infer via a probe: act() under a fixed tight-open chart
  assert pos matches ground truth: dist = (seat - button) % n; n==2: button==SB, acts first pre
fixed: n=8, seats 3 and 4 have folded, seat 5 all-in. Hero is seat 6, BTN is 7.
  assert players_to_act_after_hero == [7, 0, 1]   # SB, BB still live
  assert opponents_for_equity == live non-folded incl. all-in
```
**Impact medium, likelihood high.**

**Fixes.**
1. Compute everything from `obs` in one helper:
   `order = [(button+1+i) % n for i in range(n)]`. Players still able to act are those not
   folded and not all-in. Opponents in equity are those not folded (including all-in). Handle
   heads-up with a special case.
2. Index position charts by "seats behind me to act preflop" (0 = BTN, 1 = CO, and so on) so the
   same chart works at 6, 7 or 8 players.

### 6. `incomplete-allin-reopen-and-min-raise`
**Description.** Even with equal 100 bb stacks, an all-in for less than a full raise happens
regularly. For example, BTN raises to 1200 and the SB shoves 2000: the increment is 800, which is
smaller than the last full raise of 1140. Under standard rules this does not reopen betting for
players who have already acted, but players who have not acted yet may still re-raise. The next
min-raise is based on the last FULL raise increment, not on the short one.

Bots that compute `min_raise = 2*current_bet` or `current_bet + last_increment` from history get
this wrong. So do bots that assume they can always 3-bet or 4-bet. Their own history parser may
also miscount "number of raises" when an all-in is labelled `'call'` or `'raise'` inconsistently.

**Cost.**
- Illegal raise attempts (feeds problem 1).
- Wrong reads such as "villain 4-bet, so he has AA" when villain made a short all-in.
- If our local arena gets this rule wrong, we tune against an engine that lets us re-raise when
  the real one does not, or the other way round. Every strategy result from the arena is then
  biased in spots facing shoves, which happen often against always-all-in and random-shover bots
  in this field.

**Test scenario.**
```
engine unit tests (arena must pass):
  T1: blinds 10/20; UTG raises to 60 (inc 40); MP all-in total 90 (inc 30 < 40).
      UTG to act again: legal must be ['fold','call'] only (UTG already acted, not reopened).
      A player who had NOT acted (e.g. CO): min_raise_to == 90 + 40 = 130.
  T2: two consecutive short all-ins whose increments sum to >= a full raise
      -> reopens for players who already acted (standard TDA rule; confirm with official rules).
  T3: BB option. Limped pot, BB to act with to_call==0 -> legal includes 'raise' and 'check'.
bot test: feed T1 obs to hero as UTG; assert action in {'fold','call'}.
```
**Impact medium, likelihood medium.**

**Fixes.**
1. The bot never infers whether raising is allowed; it uses only `obs['legal']` and
   `obs['min_raise_to']`. The history parser classifies a raise by whether `amount` exceeds the
   previous street maximum, not by the action label.
2. The arena implements TDA "full raise reopens" logic with explicit tests T1–T3 (see checklist).

### 7. `pot-odds-and-side-pot-misaccounting`
**Description.** The EV or pot-odds calculation uses `obs['pot']`, which includes chips we cannot
win, or compares equity to the wrong denominator. Typical cases:
- Facing a short all-in, `to_call` is already capped, but the bot still calculates pot odds as if
  it were behind the bigger bettor.
- Multiway with one opponent all-in and another live: equity against the all-in player in the main
  pot is not equity in the side pot.
- `pot` double-counting the current-street `bets` (CONTEXT says `pot` already includes them).
- Counting folded players' dead money twice.

The opponent model can also misread `showdown.winners` as net profit when it is the gross chips
returned.

**Cost.** This is silent. Over-calling or over-folding in multiway all-in pots, which the shove-bot
field produces often. Each mistake in a 100 bb pot is expensive.

**Test scenario.**
```
fixed: 3-way, pot after preflop. Flop: A shoves 2000 total, B calls, hero to act with to_call
  equal to the remaining stack. Assert the bot's computed pot_odds ==
  to_call / (pot + to_call) using engine pot semantics, verified by a debug hook.
engine: side-pot unit test with 3 different all-in sizes (needs unequal stacks; force via a
  test-only stack override) and hero winning only the main pot.
  Assert distribution and that sum(deltas) == 0.
```
**Impact medium, likelihood medium.**

**Fixes.**
1. Define `pot_after_call = pot + to_call` exactly once, relying on the contract's statement that
   `pot` includes this street's bets, and unit-test that definition against the engine.
2. Multiway with all-ins: compute equity against the set of opponents contesting each pot layer.
   As a cheap approximation, use equity against all non-folded opponents, which is conservative.

### 8. `card-parsing-and-street-assumptions` (includes the "five betting rounds" discrepancy)
**Description.**
- Card strings arrive in an unexpected form: `'10h'` instead of `'Th'`, lowercase `'ah'`, unicode
  suits `'A♠'`, ranks as ints, a board given as `None` before the flop, or a single
  space-separated string.
- A silent parse fallback, such as an unknown rank becoming 0, leaves duplicate or missing cards in
  the Monte Carlo deck, which corrupts equity without any error.
- The street logic is keyed on string names or a fixed count of 4 rounds.

The talk notes reportedly mention "five betting rounds", but standard NLHE has four (preflop, flop,
turn, river). Possible meanings:
- (a) the speaker counted blind posting or showdown as a "round";
- (b) the official engine uses a different street enum, e.g. includes `'showdown'` or `'blinds'`
  as a `street` value;
- (c) it is a genuine variant.

Case (b) would crash a bot that does `{'preflop':0,'flop':1,'turn':2,'river':3}[street]`. Case (c)
would mean wrong equity and sizing on the extra street.

**Cost.** A crash means a failure and a fold (problem 2). Wrong equity is silent and expensive. The
likelihood is low on the current contract, but the official format has not been released yet.

**Test scenario.**
```
parse fuzz: every card in 52 x {canonical, lowercase, '10' rank, unicode suit} -> same internal id
assert len(set(hole + board)) == len(hole) + len(board) else fallback (treat as unknown, no MC)
street fuzz: obs with street in {'preflop','flop','turn','river','showdown','blinds',None}
  and board length 0/3/4/5 (+ inconsistent combos)
  -> no exception; derive street from len(board) when the name is unknown
```
**Impact high, likelihood low–medium.**

**Fixes.**
1. Use one `parse_card` function that accepts all the formats above and checks that the cards are
   unique. Derive the street from `len(board)`: 0 is preflop, 3 flop, 4 turn, 5 river, anything
   else falls back to the safe policy.
2. Re-check the official rules for the number of rounds and the street names as soon as they are
   published, and make the street mapping a single constant at the top of the file.

---

## Lower-priority notes (mostly not applicable while stacks reset every hand)
- **Busting mid-hand / dead or short blinds / a blind with stack < BB:** cannot happen with a
  2,000 reset each hand. It becomes relevant if the official format carries stacks over. Then
  `stack < to_call` calls are all-ins for less, side pots become common, and button rotation over
  busted seats matters. The bot should never assume equal stacks; read `stacks` from `obs`.
- **Odd chip in split pots:** goes to the first winner left of the button (engine rule only; no
  effect on the bot beyond ±1 chip).
- **`deltas` in `hand_end`:** use these for profit tracking, not `winners`, which are gross
  amounts.
- **Another bot timing out or acting illegally:** may appear as a forced fold or check event with
  an unusual label. Problem 2's normaliser covers it. Exploiting other bots' input handling is
  allowed by the rules; exploiting the engine is not.

## Universal fuzz harness spec (for the arena's robustness gate)
```
bots: ChaosBot (random legal action, random legal amount incl. min, max, max-1),
      ShortShover (raises to a random amount in [min, max], often just below a full re-raise),
      Staller (sleeps near the time budget; checks engine timeout handling),
      AllInEveryHand, CheckFold
tables: n in {2,3,7,8}; 50k hands; random seeds; duplicate deals
event mutator (optional layer): str keys, None amounts, unknown action labels, dropped observe
per candidate record: exceptions, illegal actions, free folds (fold when check legal),
  time p50/p99/max per n_opponents, memory at 1k/10k/50k hands
gate: 0 exceptions, 0 illegal, 0 free folds, p99 < 0.5 * budget, memory flat
```

## Engine checklist: rules the local arena must implement to match standard NLHE
1. **Blinds and order, 3+ players:** SB is the first live seat left of the button and BB is next.
   Preflop action starts left of the BB (UTG). Postflop action starts with the first live seat
   left of the button.
2. **Heads-up:** the button posts the SB and acts first preflop; the BB acts first on every
   postflop street.
3. **BB option:** in a limped pot the BB may check or raise when `to_call == 0`.
4. **Raise-to semantics:** `min_raise_to = current_bet + max(last_full_raise_increment, BB)`, and
   `max_raise_to = bets[seat] + stacks[seat]`. If `stack + bet <= current_bet`, raise is not legal
   and call is an all-in for less (call amount capped at the stack).
5. **Incomplete all-in:** an all-in raise smaller than a full raise does not reopen betting for
   players who already acted on this street; they may only fold or call. Players yet to act may
   raise, and the next min-raise uses the last full increment. Confirm against the official rules
   whether cumulative short raises reopen (TDA: yes once they sum to a full raise).
6. **`legal` set:** `check` only if `to_call == 0`, `call` only if `to_call > 0`. `raise` is absent
   when the player cannot make a full min-raise and is not all-in-capable, or when betting is
   closed to them. `fold` may be offered at `to_call == 0`, but count it as a free fold.
7. **Skip players who cannot act:** a street ends when all live non-all-in players have matched
   the bet and acted since the last full raise. If at most one player can still act and no bet is
   pending, run the board out with no further betting.
8. **Side pots:** layer the pots by each all-in total commitment. Folded players' chips go into
   the layers they reached, but those players are not eligible to win them. Each layer is awarded
   to the best hand among the eligible players.
9. **Split pots:** divide equally and give the odd chip(s) to the first winner(s) clockwise from
   the button. Check `sum(deltas) == 0` every hand.
10. **Uncalled bet:** an uncalled excess is returned to the bettor before showdown or award, and
    does not count as won.
11. **Showdown and evaluation:** best 5 of 7. The wheel A-2-3-4-5 is a straight. There is no suit
    ranking. Kickers are compared fully. Mucked hands are not revealed (decide whether the event
    shows all live hands or only winners, and match the official format when known).
12. **Four betting rounds:** preflop, flop (3 cards), turn (1), river (1), with burn cards
    optional. Make the street enum and round count configurable to absorb the "five rounds"
    ambiguity.
13. **Failures:** on an illegal action, an exception or a timeout, apply check if legal, otherwise
    fold. Log it and count it per bot. Enforce a per-decision timeout that matches the official
    budget once known (assume 50 ms typical for now).
14. **Stacks:** reset to 2,000 each hand by default. Keep a carry-over mode switch to test for
    official formats where stacks persist (busting, short blinds, button movement over empty
    seats).
15. **Events:** emit `observe` events to every bot in order, starting with `hand_start`. Keep
    seat keys as ints internally, but offer a JSON round-trip mode so the str-key issue is
    tested. Include the blind posts consistently, either in `history` or not, and document which.
