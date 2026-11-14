# Lane C analysis helpers

`analysis.py` holds stateless, standard-library helpers for hand, draw,
preflop and pot facts, written to be copied function by function into the
submitted `bot.py` (branch `poker/live`). Nothing here picks an action.

## Cost per call

Laptop, Python 3.12, best of five runs over 2,000 random hands or 3,487
engine states. The tournament machine is 10–15x slower. The live bot spends
about 0.1 ms per decision (about 0.2 s per 1,000-hand round), so a helper
called on every decision should cost well under that.

| Function | Laptop ms per call | Use |
|---|---|---|
| `call_price(state)` | 0.005 | Price of a call against only the pots we can win. |
| `hand_contributions(state)` | 0.002 | Chips each seat has put in this hand. |
| `pot_layers(contributions, folded)` | 0.002 | Main pot and side pots, with who is eligible. |
| `hand_category(hole)` | 0.001 | `AA`, `AKs`, `AKo` … (169 classes). |
| `position_info(state)` | 0.003 | Position labels in preflop action order. |
| `analyze_preflop(state)` | 0.023 | Limpers, open raiser, 3-bets, callers, reopened raising. |
| `assess_draws(hole, board)` | 0.025 flop, 0.013 turn | Outs and odds for flush and straight draws. |
| `assess_hand(hole, board)` | 0.005 / 0.022 / 0.077 | Made hand, board strength, pair labels. |
| `analyze(hole, board)` | 0.033 / 0.038 / 0.075 | `assess_hand` plus `assess_draws`. |

## What to port into the live bot

- **Base layer (layer 1):** `call_price` with `hand_contributions` and
  `pot_layers`. The live bot prices calls as `to_call / (pot + to_call)`,
  which counts chips we can't win when we call all-in for less: a 300-chip
  all-in call against a 1,000 bet into 60 needs 45% equity, not 22%.
- **Preflop reads and skills:** `analyze_preflop` and `position_info` give
  the raise count, open raiser, limpers, short all-ins that don't reopen
  raising, and seats still to act, from `state["history"]` alone.
- **Draws:** `assess_draws` labels outs that the live bot's Monte Carlo
  equity already prices. Use it for explanations or skills, not to replace
  equity.
- **Superseded:** `best_five` and `score_five` duplicate the live bot's
  `score()`; port `assess_hand` only if a skill needs its labels.

## Run the tests

The tests compare against the official engine in the starter kit, which is
vendored as `kit/` on branch `poker/live`:

```
git worktree add ../live origin/poker/live
KIT=../live/kit python3 candidates/improved/tests/test_analysis.py
KIT=../live/kit python3 candidates/improved/tests/test_preflop.py
```

## Field reference

### `analyze(hole_cards, board_cards)`
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
  - `shared_board`: draws the board makes alone.
  - `backdoor` (flop): `backdoor_flush`, `backdoor_straight` with exact
    two-card probabilities; never counted as direct outs.
  - `combined_direct_outs` / `combined`: union of direct outs, so overlaps
    are counted once.

Probabilities are the chance of hitting a fixed set of completion outs, not
of winning: next card n/47 (flop) or n/46 (turn); flop by river
1 − ((47−n)/47)·((46−n)/46). Draws are only to categories we don't hold: no
straight draws once we have a flush. Straight-flush draws, set and two-pair
improvement outs are not labelled, and outs aren't discounted for cards
that also help opponents.

### `analyze_preflop(state)`
Rebuilt from `state["history"]` on every call, so a second decision in the
same hand never double-counts.
- `hand_category`, `street`.
- `position`: `label`, `action_order_index` (0 = first to act preflop),
  `seats_in_action_order`, `labels_by_seat`, `players_dealt`,
  `original_players_behind`, `dealt_seats_source`. 8-handed
  `UTG, UTG+1, LJ, HJ, CO, BTN, SB, BB`; 7-handed `UTG, LJ, HJ, CO, BTN, SB, BB`.
  Labels are fixed at the deal; busted seats are skipped.
- `action` (`available: false` with a `reason` when history is missing,
  malformed or doesn't start with both blinds):
  - `events`: every preflop entry with `seat`, `position`, `action`,
    `amount`, `voluntary`, `bet_level_before`, `all_in`; raises add
    `raise_to`, `raise_increment`, `full_raise`, `raise_number`, `raise_name`.
  - `posted_blinds`, `limpers`, `open_raiser`, `re_raisers`, `callers`
    (`called_raise_number`, `short_call`), `folded_seats`, `pot_type`
    (`unopened`, `limped`, `single_raised`, `re_raised`), `raise_count`,
    `bet_level`.
  - Only while still preflop: `to_call`, `current_bet`, `our_bet`, `pot`,
    `min_raise_to`/`max_raise_to`, `raises_this_street`, `decision_number`,
    `our_previous_actions`, `raising_reopened_for_us`, `can_raise_now`,
    `opponents_in_hand`, `opponents_all_in`, `still_to_act_after_us`, and
    `consistent_with_state` (plus a `warning` when the replay doesn't match
    the state).
