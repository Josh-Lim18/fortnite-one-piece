# Mechanics integration (current status)

The bot now runs hand/draw and preflop analysis plus table state, pot odds, side-pot eligibility, lifecycle accounting and a random legal policy. The starter fallback is removed. All analysis is available on `agent.analysis`; existing card and preflop results are under `agent.analysis['extra']`. Replace `random_policy` to add strategy; retain `legalise_action`.

Validated with Python 3.12: 35 analysis tests and 9 mechanics tests, 1,200 multi-format hands and two 1,000-hand official timed-runner rounds. Zero errors/timeouts/bank exhaustion; measured peak IPC decision 2.813ms before the compatibility-only starting_stack alias. Approximately 30.2KB. No preflop tables or competitive policy.

Run `python candidates/improved/test_mechanics.py PATH_TO_KIT`. Existing tests use the `KIT` environment variable. Starting-stack-derived contributions are checked against the public pot; unavailable totals yield None. Side-pot thresholds assume no further betting and may require separate equity per pot. Positional order is not the pending-action queue.

The historical integration notes below describe the analysis APIs; statements about a starter fallback are superseded by this section.

---

# Lane C: hand, draw and preflop analysis (integration note)

**Status.** Hand/draw analysis and preflop analysis are complete and tested.
This does **not** replace the starter strategy: the betting strategy and
preflop tables are **pending**, and `select_action` still runs the starter
kit's rules as a labelled **temporary fallback**. Not merged, not submitted.

## Files
- `bot.py`: self-contained submission file (24.9 KB, stdlib only).
- `tests/test_analysis.py`: 20 tests (hands and draws).
- `tests/test_preflop.py`: 15 tests (preflop), using real engine states.
- Run either with `KIT=<starter kit> python tests/<file>.py`.

## Pipeline
`Agent.act(state)` → `analyze(hole_cards, board)` plus
`analysis["preflop"] = analyze_preflop(state, starting_stack)` →
`select_action(state, analysis)`. The replacement policy only changes
`select_action`. If `analyze` raises, `act` passes `None`; if only
`analyze_preflop` raises, `analysis["preflop"]` is `None`. A decision is
always returned.

## `analyze_preflop(state, starting_stack=None)` returns
Everything is derived from `state["history"]` on each call, so a second
decision in the same hand never double-counts, and nothing carries over
between hands.
- `hand_category`: one of 169 classes, higher rank first (`AA`, `AKs`, `AKo`, `76s`).
- `position`: `label`, `action_order_index` (0 = first to act preflop),
  `seats_in_action_order`, `labels_by_seat`, `players_dealt`,
  `original_players_behind`, `dealt_seats_source`.
  Labels in preflop action order: 8-handed `UTG, UTG+1, LJ, HJ, CO, BTN, SB, BB`;
  7-handed `UTG, LJ, HJ, CO, BTN, SB, BB`. SB is the first dealt seat after
  the button, as in the engine. Labels are fixed at the deal: folds never
  relabel anyone. Seats that weren't dealt in (busted seats that are folded
  with no history) are skipped.
- `action` (`available: false` with a `reason` when history is missing,
  doesn't start with both blinds, or has a malformed entry):
  - `events`: every preflop entry in order, with `seat`, `position`,
    `action`, `amount`, `voluntary` (blinds are not), `bet_level_before`,
    `all_in`. Raises add `raise_to`, `raise_increment`, `full_raise`,
    `raise_number`, `raise_name` (`open_raise`, `3bet`, `4bet`, ...).
  - `posted_blinds`, `limpers` (calls before any raise, including the SB
    completing), `open_raiser`, `re_raisers`, `callers` (with
    `called_raise_number`, `short_call` for all-in calls for less),
    `folded_seats`.
  - `pot_type`: `unopened`, `limped`, `single_raised` or `re_raised`;
    `raise_count`; `bet_level`.
  - Only while it's still preflop: `to_call`, `current_bet`, `our_bet`, `pot`,
    `min_raise_to`/`max_raise_to`, `raises_this_street`, `decision_number`,
    `our_previous_actions`, `raising_reopened_for_us` (false after an
    incomplete all-in raise if we've already acted, as the engine rules),
    `can_raise_now`, `opponents_in_hand`, `opponents_all_in`,
    `still_to_act_after_us` (seats the engine will still ask to act after
    us), and `consistent_with_state` (the replay reproduces the state's bets,
    folds and raise count; otherwise a `warning` is added).

Unavailable information: no hidden cards or opponents' stacks beyond the
state. All-in flags after preflop need `starting_stack` from
`on_table_start`; without it they are `None`. If history is missing,
positions use unfolded seats only (`dealt_seats_source` says so).

## `analyze(hole_cards, board)` returns
- `street`, `hole` (high, low, pocket_pair, suited).
- `hand` (flop onwards): `category`/`category_name`, `score` (engine-compatible
  tuple), `best_five`, `hole_cards_used`, `board_category`, `board_score`
  (river), `hole_contribution` (`improves_board_category`, `kicker_only`,
  `none_plays_board`), `plays_board` (river only), `board_paired`,
  `pairs_with_hole_cards` (overpair, underpair, pocket pair between board
  ranks, top/middle/bottom pair with kicker).
- `draws` (flop and turn; `applicable: false` preflop and on the river):
  - `direct`: `flush_draw`, `open_ended`, `gutshot`, `double_gutshot`, each
    with `out_cards`, `outs`, `next_card`, and on the flop `by_river`.
  - `shared_board`: draws the board makes alone (our hole cards add nothing).
  - `backdoor` (flop): `backdoor_flush`, `backdoor_straight` with exact
    two-card probabilities; never counted as direct outs.
  - `combined_direct_outs` / `combined`: union of direct outs, so overlaps
    (e.g. a straight-flush card) are counted once.

Probabilities: next card n/47 (flop) or n/46 (turn); flop by river
1 − ((47−n)/47)·((46−n)/46). They are the chance of hitting a fixed set of
completion outs, **not** the chance of winning.

## Validation (Python 3.12.10, official kit engine)
- 45,000 random 5/6/7-card hands plus named edge cases (wheel, steel wheel,
  six-high vs wheel, flush kickers, two trips, three pairs, quads kickers,
  royal over a lower straight flush) match `engine.cards.evaluate` exactly.
- Draw examples checked by hand: flush 9 outs, open-ended 8, double gutshot 8,
  ace-low gutshot and open-ended, combo draw 15 (overlap counted once), turn
  n/46, shared-board flush and straight, a hole card that beats a board
  straight, backdoor flush 90/2162 and backdoor straight 96/2162.
- Fallback returns exactly the starter's action on every engine state across
  7/8 seats and no-limit, pot-limit and fixed-limit with a raise cap of 3.
- `analyze` runtime on this laptop: mean 0.04 ms flop/turn, 0.08 ms river;
  max 0.11 ms. Kit `local_sim.py`, 2 × 1,000 hands: 0 timeouts, 0 errors,
  worst round 0.4 s of the 10 s bank.

## Limitations
- Draws cover flushes and straights only, to categories we don't already hold.
  Set/trips/two-pair improvement outs and straight-flush draws are not labelled
  separately (straight-flush cards still appear once in the combined outs).
- Outs aren't discounted for cards that also help opponents (e.g. a flush out
  that pairs the board).
- `kicker_only` means our category equals the board's; it doesn't say whether
  the kicker is relevant.
- Not yet run through lane D's `tests/check_submission.py` (PR #4 is unmerged).

## Preflop validation (Python 3.12.10, official kit engine)
- Hand categories: all 1,326 two-card combos map to exactly 169 classes
  (6 per pair, 4 per suited, 12 per offsuit hand).
- Positions: every seat, at every button position, at 7 and 8 seats.
- Scripted engine hands: unopened, limpers, raise + call + 3-bet, a repeat
  decision with no duplicated events, a short all-in raise that doesn't
  reopen raising (plus a short all-in call), and a busted seat at an
  8-seat table.
- Missing history, missing blinds, malformed entries and a dropped event
  are all reported as unavailable or inconsistent, never guessed.
- Random engine play, 7/8 seats, no-limit/pot-limit/fixed-limit: 5,486
  decisions, all consistent with state. `analyze_preflop` mean 0.022 ms,
  max 0.41 ms. Kit `local_sim.py`, 3 × 1,000 hands: 0 timeouts, 0 errors,
  worst round 0.8 s of the 10 s bank.

