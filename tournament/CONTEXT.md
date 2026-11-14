> Historical brief from tournament day. The local arena it mentions (`tournament/arena`) is not included in the repo;
> reproduce with `arena/` or `tools/sim.py` on `poker/live`.

# Strategy tournament — shared context (read this first)

Team: Imperial AI Hack poker-bot track (repo Josh-Lim18/fortnite-one-piece). Local, read-only clone: nothing here is pushed.

## Game (team reference; official rules not yet available — re-check later)
- No-limit Texas hold'em, 7–8 players per table, 2,000-chip stacks, blinds 10/20 (100 big blinds deep).
- Stacks reset every hand. Score = bb/100 (big blinds won per 100 hands). Pure chip EV: no ranking/variance considerations.
- Raises are "raise to" (total street commitment), not "raise by".
- The field is ~11 other student bots built in a weekend: expect rule-based bots, always-all-in bots, random-timer shovers, calling stations, tight-passive bots, a few opponent-modelling/adaptive bots, and possibly deceptive bots.

## UPDATE: official API and incumbent
The team's adapted bot (`candidates/incumbent/bot.py`, VIVelev Monte Carlo) is the incumbent and shows the official API:
`Agent()` (no args), optional `on_table_start(info)`, `act(state)` with keys `hole_cards, board, legal_actions, min_raise_to, max_raise_to, folded, seat`.
The arena state includes both those names and the local names below. Candidates are built from `candidates/improved/v0_skeleton/bot.py` (incumbent refactored into hooks). See `SOLVER_BRIEF.md`.

## Candidate contract (local adapter; superseded where it conflicts with the update above)
One standalone Python file exporting `Agent`. Standard library + numpy only (no pip installs available).

```python
class Agent:
    def __init__(self, seat: int, num_players: int, rng_seed: int): ...
    def act(self, obs: dict) -> dict: ...        # must return a legal action, fast (< 50 ms typical)
    def observe(self, event: dict) -> None: ...  # optional; every public event at the table
```

`obs` keys: `hand_id, seat, num_players, button, small_blind, big_blind, hole (list of 2 card strings like 'Ah','Td'), board (list), street ('preflop','flop','turn','river'), pot (chips in pot incl. current street bets), stacks (list, chips behind), bets (list, this-street commitment per seat), folded (list bool), all_in (list bool), to_call (chips needed to call), min_raise_to, max_raise_to (raise-to totals; max = all-in), legal (subset of ['fold','check','call','raise']), history (list of action events this hand)`.

Action: `{'action': 'fold'|'check'|'call'|'raise', 'amount': raise_to_total}` (`amount` only for raise). Illegal or exceptional actions are counted as failures by the robustness gate (engine then folds/checks for you).

Events passed to `observe`: `{'type':'hand_start', hand_id, button, stacks}`, `{'type':'action', hand_id, seat, street, action, amount, pot}`, `{'type':'board', street, board}`, `{'type':'showdown', hand_id, hands: {seat: [c1,c2]}, winners: {seat: chips}}`, `{'type':'hand_end', hand_id, deltas: list}`.

## Arena (tournament/arena)
- `engine.py` — table engine with side pots and duplicate deals; `evaluator.py` — 7-card evaluator + equity helpers; `bots/` — dummy opponents; `run.py` — matches with seat rotation, bb/100 ± 95% CI, robustness counters.

## Phases
1 Scout problems → 2 parallel solvers per problem (balanced / exploitative / minimal patch / wildcard) → 3 arena (robustness gate, problem scenario, general field, regression vs incumbent) → 4 winner + backups with trigger conditions → 5 package to `candidates/improved/`.

## Rules
- Never modify the incumbent. Work only in the files you are told to own.
- Label strategy claims as hypotheses until they pass the arena.
- Exploiting opponent bots' handling of unusual inputs is fine; exploiting the competition engine/infrastructure is not.
