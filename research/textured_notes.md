# dev.fun Textured: B public-policy port

Status: standalone candidate implemented; local source-differential and official-state legality checks pass. Actual Python 3.12.10 Windows testing and serial subprocess checks are recorded below; platform readiness remains pending. This is a public reference strategy for the arena, not a selected winner or C-stage improvement.

## Source and license

- Repository: [`devfun-org/poker-arena-starter-kit`](https://github.com/devfun-org/poker-arena-starter-kit).
- Exact source: [`assets/decide_textured.py` at `fc19bb25e9c6e8fabc26099d6a767241fc99fc2f`](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/assets/decide_textured.py).
- Source Git blob SHA: `f60d4bceb8d4c691c1f62f159a21e88eb0e6efbc`.
- [License at the same commit](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/LICENSE): MIT, copyright 2026 dev.fun; Git blob SHA `10c274feb801755eab152d057fb9c2345fe8097a`.
- Full source and license fetched through the GitHub connector and inspected before execution. They are preserved in `research/sources/textured_upstream.py` and `research/sources/textured_LICENSE.txt`. The complete MIT notice is also inside the standalone candidate.
- Upstream calls this “Reference implementation #3”; this intake has not independently established its competitive quality. The repository's broad performance descriptions are not measurements of this port.

Local file checksums:

| File | SHA-256 |
|---|---|
| `research/sources/textured_upstream.py` | `7e4e5e98bdc1787d93c2982aad8a6640050331e55c7b6b8e040da953da0a9739` |
| `research/sources/textured_LICENSE.txt` | `16eb8f74f62cc4b0de5434f68bc70b7698b33df426f5436f2469931eff2324f6` |
| `candidates/imported/devfun_textured.py` | `88af4ca6c6962c6590a2beed68a4df5ca6143d95aa2131bec16ea3f762208b74` |

Candidate size: **11,098 bytes**. Its sole import is standard-library `typing`. It is stateless and deterministic, needs no runtime files, network access, training or external packages, and exports `Agent.act(state)`.

## Exact adaptation decisions

The opening-range sets, board classifier, street classifier, hand-class helper, sizing fractions, defense range and coarse postflop decisions are retained from the source. The source `decide` function has only two semantic edits: remove its `<2 seconds` fallback gate, and permit its opening branch when the Imperial state is an unraised pot facing only blinds. The remaining changes are the Imperial state/action wrapper and position mapping. Reviewed cleanup removed an obsolete upstream usage/performance docstring, without changing policy behavior; the untouched original remains preserved.

1. **Deadline gate:** the source immediately checks/folds whenever its `deadline_s` is below 2 seconds. Imperial permits 10ms; this constant-cost rule-based policy needs no such gate. The wrapper passes `0.010` without suppressing an otherwise valid decision. This does not pretend to enforce a hard wall-clock deadline; the official runner remains responsible for it.
2. **Positions:** the source ties six ranges to absolute seat numbers. `_position` instead uses `(seat - button) % player_count`, then maps to the source's canonical six positions. Extra early seats receive the existing UTG range; no new ranges were invented.

| Clockwise positions starting at the actual button | Mapping |
|---|---|
| Six players, for source comparability | BTN, SB, BB, UTG, MP, CO |
| Seven players | BTN, SB, BB, UTG, UTG, MP, CO |
| Eight players | BTN, SB, BB, UTG, UTG, UTG, MP, CO |

3. **Unraised blind-facing pots:** the source opens only when `call_chips == 0`, which would suppress nearly every ordinary Imperial first-in opening. The adapter recognizes preflop pots with no voluntary raise in history and no current street bet above the big blind. It allows the opening branch there while preserving the real call price for every subsequent defense decision. Calls/limps do not count as raises. A live bet above the blind or a recorded raise prevents this added opening path.
4. **Raise-to amounts:** both protocols use total chips committed this street. The upstream fixture explicitly records `amountSemantics: "toAmount"` and `amountHint: "total committed this street"`; the exact excerpt and source link are saved in `research/sources/textured_amount_contract.md`. The adapter supplies Imperial's legal minimum/maximum total, clamps the source amount, and returns `raise`. It never adds the player's previous contribution again. Short all-in ranges where minimum equals maximum, fixed-limit amounts, pot-limit caps and closed raising are respected.
5. **Output:** the wrapper returns only the action and, for raises, integer amount. Upstream explanatory message/reasoning strings are not part of the Imperial action contract. Illegal fallback folds become checks when check is the free legal action.

The source's opening formula is `min(2 * minimum_raise_to, maximum_raise_to)`, despite an internal explanatory string saying “2.5bb open.” In a normal Imperial unraised no-limit pot, minimum raise-to is 40, so this port opens to **80 chips / 4BB**. That formula was preserved, not silently retuned.

## Preserved strategy limitations

- Postflop strength is only a test of whether any hole-card rank appears on the board. It does not evaluate poker hands, equity, draws or kicker quality. A pocket overpair can check/fold on an unmatched board, and a made straight or flush with no shared rank can fold to a bet. Tests deliberately preserve these flaws.
- Board texture uses overall rank span and suit counts; it does not handle ace-low connectivity specially. `A-2-3` rainbow is classified dry. The classifier returns only dry/wet on normal postflop boards; neutral sizing is essentially unused there.
- The postflop code has no actual position adjustment, despite the upstream docstring referring to one. Position only selects preflop opening ranges in this implementation.
- Preflop defense uses one fixed range regardless of the raise size, number of opponents or position. It can call very large bets with the same nominal defending range.
- The policy does not learn opponents or model multiway ranges. Seven/eight-player tables receive a documented conservative mapping into six existing ranges, not a freshly calibrated multiway strategy.

These behaviors make the candidate a useful distinct, inexpensive reference for B's arena intake. They do not establish that it should be submitted or improved next. Any repairs to these policies belong in a separately measured C-stage variant.

## Verification

Local interpreter: **Python 3.12.10 Windows**, actual execution. Run from the repository root:

```powershell
& '../kit-review-helpers/python31210/python.exe' -B research/checks/test_textured.py
```

Set `POKERBOTS_KIT` to the extracted official kit if it is not at the test's sibling default `../kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit`.

Result: **10 focused tests passed**, included in the final 48-test Python 3.12 suite ([log](runs/unit-tests-python312-final.txt)).

- Exact opening-range and sizing equality; 1,000 hand-class and 3,000 board-texture comparisons with the preserved source.
- All **149** six/seven/eight-player seat/button combinations, preserving the source's six-seat interpretation and testing every extended mapping. AA opens legally in each combination.
- Direct tests for an actual blind-facing CO open, retained call price, recorded-raise exclusion, deadline-gate removal, total raise-to amounts, pot-limit cap, short all-in bounds and unavailable raises.
- **3,000** source-action differential comparisons where the mapping is valid and the intentional unraised-opening change is inactive.
- **2,108 real official-engine states** from 18 short eight-hand tables: seven/eight players × no-limit/pot-limit/fixed-limit × starting stacks 35/55/2,000. These are legality fixtures, not performance benchmarks. Each table included the candidate in one seat and exploratory players to exercise bounds. Zero illegal candidate actions; chip conservation held in all 144 hands.
- The real-state set includes **1,610 additional source-action comparisons**, **301 all-in bounds**, **820 single-amount raise ranges**, **756 closed-raising states**, and every street (1,457 preflop, 349 flop, 176 turn, 126 river).
- Python 3.12 grammar, standard-library-only import and conservative 200KB size checks.

Real-state breakdown:

| Players | No limit | Pot limit | Fixed limit |
|---|---:|---:|---:|
| 7 | 245 | 307 | 461 |
| 8 | 292 | 354 | 449 |

The official kit was read and imported unchanged. The initial [eight-seat Python 3.12 report](runs/python312-8-1501.json) records **one Textured timeout** on its 11,493-byte pre-cleanup file (SHA-256 4f244745c2fa2f6731a55e7565e5bb9d0cc26acd625bf19f7cd0fcecd4bf3dae). This failure is retained, and its cause is not established.

The [final eight-seat](runs/python312-8-1501-final.json) and [final seven-seat](runs/python312-7-1502-final.json) reports both match the current 11,098-byte file. Textured recorded zero timeouts, errors, invalid actions and bank exhaustion in each 1,000-hand round at default limits. The final eight-seat batch still contains a Floorfix timeout. These finite local observations do not certify repeated reliability or sealed-platform timing, and no competitive winner is inferred. See [independent expansion review](REVIEW_B_EXPANSION.md).

The initial adapter task created only `candidates/imported/devfun_textured.py`, `research/checks/test_textured.py`, `research/textured_notes.md` and the `research/sources/textured_*` files. Subsequent coordinator integration owns the shared research records and feature-branch delivery. No arena, release bot or shared root configuration was changed by this port.
