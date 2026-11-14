> Historical brief from tournament day. The local arena it mentions (`tournament/arena`) is not included in the repo;
> reproduce with `arena/` or `tools/sim.py` on `poker/live`.

# Solver brief (Phase 2)

Read `tournament/CONTEXT.md` for the game, then this file. Scout reports are in `tournament/scouts/*.md` (read the ones relevant to your problem).

## What you are building
A candidate = **a copy of `candidates/improved/v0_skeleton/bot.py` with ONLY your assigned hook(s) changed** (plus private helper functions/classes you add right next to your hook, prefixed with your problem id, e.g. `_sd_` for shove-defense). Do not edit other hooks, the evaluator, `sanitize`, `S()` or the Agent routing. Do not edit `OpponentStats`; if you need more opponent data, define your own tracker class (prefixed with your id) with `observe(event)` and append it to `EXTRA_TRACKERS` in your section; read it via `agent.trackers['<ClassName>']`. `agent.stats` (OpponentStats) gives per-seat counts: hands, vpip, pfr, shove_pf, fold_vs_bet, faced_bet, bets_raises, calls, showdowns; `agent.stats.rate(seat, num, den, prior, k)` gives a shrunk rate. Incumbent raises already pass through `hook_sizing` (intent 'value' or 'thin_value').

Save to: `candidates/improved/tournament/<problem-id>/<approach>.py` (approach ∈ balanced, exploitative, minimal, wildcard). Also write `candidates/improved/tournament/<problem-id>/<approach>.md` with: what you changed, the self-test results table, and a one-paragraph rationale **including when this solution should NOT be used** and a **trigger condition** the live bot could detect for when it is most useful.

## Official API facts (inferred from the team's adapted bot)
- `Agent()` takes no constructor args; `on_table_start(info)` may be called with `seat`; `act(state)` returns `{'action': 'fold'|'check'|'call'|'raise', 'amount': raise_to_total}`.
- Confirmed keys: `hole_cards, board, legal_actions, min_raise_to, max_raise_to, folded, seat`. All other keys (pot, to_call, stacks, bets, button, street, big_blind, history, hand_id) are local-arena guesses: read them via `S(state, key, default)` and degrade gracefully if missing.
- `observe(event)` may not exist on the official platform; the skeleton falls back to replaying `state['history']`. Never rely on observe alone for correctness; the bot must still play sensibly with an empty opponent model.
- Time: the incumbent thinks ~1.2 ms per action. Keep **mean < 3 ms and max < 50 ms** per decision in the arena. Precompute tables at import time only if import takes < 1 s; prefer embedding small literal tables.
- Standard library only (+ nothing else). One standalone file.

## Self-testing (use the arena; 2 CPUs are shared by many agents, so keep runs modest)
From `tournament/`:
```
python3 -m arena.compare --cand file:../candidates/improved/tournament/<id>/<approach>.py \
    --fields <your-scenario> gen_soft gen_shover gen_tough opponent-model --deals 300 --workers 1
```
`diff` is your paired gain vs the incumbent in slot 0 (same deals, all seats rotated). Fields are in `arena/fields.py`; dummy bots in `arena/bots/dummies.py`. You may add a scenario-specific dummy bot in a NEW file `arena/bots/extra_<problem-id>.py` and register it via a field in your own script, but do not edit shared arena files.
Requirements before you finish: 0 errors, 0 illegal actions, 0 timeouts; positive diff on your scenario; not significantly negative on any general field. Report the table in your .md.

## Labels
Every strategy claim is a hypothesis until it passes Phase 3. Exploit opponent bots, never the engine.

## Final message
Return: file path, one-line summary, self-test table (field, diff ± CI, mean ms), trigger condition, do-not-use-when.
