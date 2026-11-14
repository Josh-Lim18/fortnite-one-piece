# Lane C: hand and draw analysis (integration note)

**Status.** Analysis is complete and tested. The replacement betting strategy
and preflop tables are **pending**; `select_action` still runs the starter
kit's rules as a labelled **temporary fallback**. Not merged, not submitted.

## Files
- `bot.py`: self-contained submission file (13.8 KB, stdlib only).
- `tests/test_analysis.py`: 20 tests. Run with `KIT=<starter kit> python tests/test_analysis.py`.

## Pipeline
`Agent.act(state)` → `analyze(hole_cards, board)` → `select_action(state, analysis)`.
The replacement policy only changes `select_action`. If `analyze` ever raises,
`act` passes `None` and still returns a decision.

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
