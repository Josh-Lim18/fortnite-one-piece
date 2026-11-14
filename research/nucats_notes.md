# NUCATS starter: faithful source adapter

Adapted on **2026-11-14**. Candidate: `candidates/imported/nucats_starter.py` (5,682 bytes). This is B source intake: a deliberately weak made-hand/pot-odds comparison policy. It is not a selected winner or a C strategy improvement.

## Provenance and reuse

Repository: [nucats-soc/NUCATS-Pokerbot](https://github.com/nucats-soc/NUCATS-Pokerbot), pinned revision `67cadea4486039ef279c6e4718e3b90d58134939`.

| Upstream source | Local preserved copy | Git blob SHA-1 |
|---|---|---|
| [bots/my_bot.py](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/bots/my_bot.py) | `research/sources/nucats_bot_upstream.py` | `e7c26b10cd83017cdceaf5848b8de78f18031cec` |
| [bots/pokerbot/cards.py](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/bots/pokerbot/cards.py) | `research/sources/nucats_cards_upstream.py` | `dd509f079524d5b72edc7f7001c24646c2d4a253` |
| [LICENSE](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/LICENSE) | `research/sources/nucats_LICENSE.txt` | `a21fef204cd99bb4031be9076ac095a330a31c4e` |

The complete MIT license, copyright (c) 2026 NUCATS, is embedded in the standalone candidate and preserved separately. Original source files were read before execution; their exact blob hashes are checked by the tests. No upstream network client or runner is executed.

The source [GameState.pot_odds property](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/bots/pokerbot/state.py) was also inspected: `to_call / (pot + to_call)`, or zero when checking is free. That file's blob is `2c6bac20e469ae7e73438e4173c0e8918178876f`.

## Preserved policy

- Preflop, pocket nines or better are strong. Postflop, the original helper's strength score at least 0.7 is strong.
- When strong and raising is legal, raise **to** the smaller of three times the minimum raise total and the legal maximum.
- Otherwise check when free. Facing a bet, call when strength is at least 0.3 **or** pot odds are at most 0.2; otherwise fold.
- The decision-used card scoring helpers are flattened with unchanged scoring. Unused display helpers (card_name, describe_hand and their name tables) were removed during reviewed cleanup; the complete original remains under sources/. It uses only `collections.Counter`; there are no models, tables loaded from disk, network operations, random sampling or heavy import-time work.

Known weaknesses are deliberately preserved. A board-only pair can qualify for a strength-based call even against an expensive bet; two pair made entirely by the board can trigger a raise. The source comment says three of a kind, but the actual 0.7 threshold already includes two pair. Pair strength uses high hole-card rank without meaningful kicker/range analysis. Neither policy nor helper conditions decisions on opponent count, position or stack survival.

## Imperial mapping

| Source | Imperial mapping |
|---|---|
| `state.my_cards` | `state["hole_cards"]`; card format already matches rank then suit |
| `board`, `street`, `pot` | Same values in the official dictionary |
| `can_raise`, `can_check` | Membership of `raise` / `check` in `legal_actions` |
| `min_raise`, `max_raise` | Official `min_raise_to`, `max_raise_to`, only accessed when raising is legal |
| `pot_odds` | Ratio using official stack-capped `to_call` and inclusive pot |
| Action constructors | Dictionary actions accepted by `Agent.act(state)` |

Both protocols express raises as the total for the current street. Existing street contributions are **not** added again. Imperial's bounds handle no-limit, pot-limit, fixed-limit, short raises and raise caps; the adapter does not recalculate them from stacks.

There is no hardcoded source starting stack. Chip amounts remain in official units; hand scores and pot-odds ratios are unchanged at Imperial's 2,000-chip reset stacks. The source ignores seat/button and opponent lists, so adding position or an opponent model would be a strategy change. Seven/eight seats and zero-stack all-in opponents require no new policy logic; the supplied legal action list determines available actions.

The adapter is stateless and does not mutate the public state. Optional table/hand lifecycle callbacks are unnecessary. It never returns an `all_in` alias: a short or full-stack legal raise uses the actual bounded `raise` amount.

## Focused validation

Command:

```text
python research/checks/test_nucats.py
```

Set `POKERBOTS_KIT` to the official kit directory when it is not at the default sibling path `../kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit`.

**11 focused tests passed** on actual local **Python 3.12.10 Windows**, as part of the final 48-test suite:

- Exact upstream blob hashes for policy, helper and MIT license.
- 1,200 seeded source-vs-port comparisons across all four streets, seven/eight seats, varied call amounts and open/closed/short raise bounds. The inspected original `decide` function is extracted with AST and provided the original helper plus action-constructor stubs; no source client or runner is imported.
- Original high-pair threshold, board-only pair/two-pair behavior, and the exact 0.2 pot-odds boundary.
- Raise-to semantics with existing bets, fixed/short maximums, unavailable raises, free checks and stack-capped calls.
- Official engine-generated states from **42 isolated betting phases** covering seven/eight seats, all four streets, all three betting structures, cap-closed raising, short all-ins that do not reopen action, and calls/checks against all-in opponents. These focused probes call the actual official betting-round state producer; separate full-round integration reports are listed below.
- Standalone size, complete embedded MIT notice, only stdlib `collections` import, and parsing under Python 3.12 grammar.

Final candidate SHA-256: bd01e82f89ccb408523e96e6e9940c06b16202b71882091c6bd7346c9b09a298. The final 48-test log is [unit-tests-python312-final.txt](runs/unit-tests-python312-final.txt); independent review is [REVIEW_B_EXPANSION.md](REVIEW_B_EXPANSION.md).

The two matching-file reports [eight seats](runs/python312-8-1501-final.json) and [seven seats](runs/python312-7-1502-final.json) each exercise 1,000 hands at 10ms/action and a 10s bank. NUCATS recorded zero timeouts, errors, invalid actions and bank exhaustion in both. The initial eight-seat report used the 6,513-byte pre-cleanup file (SHA-256 9d23681daf0f0a3aa9af85ce7d375edcc2641f5a926ac4c738f4bff9e096df37); it is preserved. Other candidates timed out in this batch's eight-seat reports, so there is no blanket reliability pass. Sealed-platform behavior and competitive strength remain unverified.

## Separate D gate integration

The current candidate also passed D PR #4's local gate at revision 033851cf22f086267c5ac6defce46a14748d5528 on Python 3.12.10. Four 1,000-hand rounds covered no-limit, pot-limit, fixed-limit and no-limit with raise cap 3. **Fixed-limit recorded one timeout in 3,524 decisions (0.03% displayed)**; the other three recorded none. All four had zero errors/bank-outs. The gate exited 0 because it permits <=1% timeouts and <=5s thinking per round. This does not establish zero-timeout reliability or platform readiness. [Raw report](runs/d-pr4-gate-python312.json); [method and provenance](D_GATE_INTEGRATION.md).

## Handoff

The adapter is ready for integration as `nucats_starter`, labelled **weak public reference / made-hand baseline**. Root owns registration, execution reports, review, timing and any promotion decision. The shared shortlist and manifest now register all five adapters; use the manifest's current hashes and per-report history.
