# Independent review of B's first candidate batch

Review date: 2026-11-14. Reviewer: separate `review_b_imports` agent; no candidate implementation authored by this reviewer. Verdict: **the three adapters are suitable for intake into A/D's evaluation queue. No competitive winner or official-sandbox readiness is established.**

The review began with the official state/action contract, raw candidate and builder code, preserved upstream sources and tests. Adaptation notes and the shortlist were read only after initial code findings were sent to the orchestrator. Source comments were visible. This was a narrative-blind initial pass, not a comment-stripped review.

The local directory is a source snapshot, not a Git checkout. Remote baseline supplied by the orchestrator is `bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d`. No final commit SHA existed at review time; exact reviewed candidate bytes are identified below. The review covers new B files, with no requested modification to root, arena, engine or release files.

## Findings and resolution

1. **Resolved: smoke reliability omitted live process state.** The initial helper collected `dead` after `close()` and did not gate on dead/stalled/flooded processes. Normal shutdown can change `dead`, while a stopped process must never be accepted solely because earlier counters were zero. The orchestrator changed the helper to snapshot `dead`, `stalled`, `flooded` and `proc.poll()` immediately after play, before teardown, and reject any candidate with those failure signals. I re-read the revised control flow and gate. Earlier reports remain historical evidence under the older helper; fresh reports should use the revised helper.
2. **No blocking candidate defect found.** Floorfix's broad source exception fallback warrants scrutiny because errors could otherwise look like valid folds. An independent trace over real generated states observed no swallowed `Exception` instances in the candidate. This is finite coverage, not proof that all possible states are bug-free.
3. **Target execution remains unverified.** Python 3.12 grammar parsing on Python 3.14 does not execute the target interpreter or reproduce the organizer's sealed sandbox. The notes disclose this correctly. Full subprocess results must retain the actual interpreter and limits, and failures must not be reclassified as passes.

The initial exception-trace probe incorrectly counted normal generator shutdown (`GeneratorExit`, a `BaseException` subclass). The probe was corrected to track actual `Exception` subclasses, then repeated successfully. No implementation fix was needed for that instrumentation false positive.

## Criterion assessment

| Criterion | Status | Evidence and limit |
|---|---|---|
| Standalone `Agent` files under 200,000 bytes | PASS | Floorfix 34,881 bytes; Shark 3,684 bytes; VIVelev 6,260 bytes. Runtime imports are only `random` and, where needed, `time`. No runtime file/network/process operations or model loading found. |
| Official state and total raise-to mapping | PASS | Raw code uses the official legal actions and raise bounds, including closed raising, capped/short all-ins and fixed-limit bounds. Floorfix uses the supplied big blind rather than upstream's hardcoded 100. |
| Seven/eight seats and alternative structures | PASS for tested states | Independent probe checked 324 actions per candidate across 7/8 seats, no-limit/pot-limit/fixed-limit, raise cap 3, and all four streets. Every action and raise amount was legal. This is not a full state-space proof. |
| Hand evaluator ranking, ties and edge hands | PASS | Existing suite passed 12,000 exact comparisons to the official evaluator plus 1,200 comparisons to a separate combinations-based oracle; wheel, full house from two trips, three-pair kickers, flushes and board ties covered. Raw bitset/packed-score implementation inspected. |
| All-in opponents distinguished from folds | PASS | Both equity policies count `folded == false` seats regardless of zero stack; focused regression tests and adapter code confirm this. |
| Source-policy attribution and deviations | PASS | Preserved originals and licence text inspected. Floorfix thresholds/sizing/survival behavior remain identifiable; reduced samples, evaluator, state/history and chip-unit changes are disclosed. VIVelev keeps strict thresholds and ties-as-full-wins, while documenting current-live-opponent counting and reduced samples. Shark's rank and absolute-seat flaws are explicitly retained. |
| No mutable gameplay state shared across agents | PASS | Private RNGs; Floorfix counts owned by each Agent, reset at table start; completed histories deduplicated; current-hand merging occurs on copies. Embedded equity lookup is read-only in gameplay. |
| Useful failure/regression coverage | PASS | Boundary actions, source differential cases, evaluator oracles, live all-in counting, profile deduplication and clock-boundary checks exercise meaningful behavior. These are more than compilation checks. |
| B stays separate from C and the arena | PASS | Ports and research notes do not declare a winner; the smoke helper imports the supplied engine unchanged and runs one intake table. Source survival assumptions and MC noise remain documented limitations for later selection/tuning. |
| Smoke result failure accounting | PASS by revised-code inspection | Revised helper records live process flags before close, gates counters and flags, checks chip conservation, records engine/candidate hashes and refuses to overwrite an existing output file. Full-round runs are orchestrator-owned. |
| 10 ms/decision and 10 s/round on Python 3.12 platform | UNVERIFIED by this review | Soft internal budgets leave intended IPC headroom but cannot guarantee wall-clock latency. Reviewer did not run competing full-round timing jobs. Use fresh orchestrator reports and then the exact platform acceptance check. |
| Competitive strength and robust selection | UNVERIFIED | A few smoke tables cannot rank the candidates. Seat rotations, diverse opponent pools, withheld evaluation and uncertainty remain D's work. |

## Checks actually performed

Using the installed Python 3.14.6 interpreter from the repository root:

```text
python -m unittest discover -s research/checks -p test_*.py -v
```

Observed: **27 tests passed in 0.597 seconds**. The suite's small in-process Floorfix timing probe printed median 0.576 ms, p95 0.908 ms, p99 1.106 ms and maximum 1.246 ms. These figures exclude IPC and are not used as timing acceptance evidence.

An additional reviewer-owned ephemeral probe imported each candidate with `importlib`, then used the unchanged `FixedHandsTable` to generate states. Configuration: seat counts 7 and 8; each of no-limit, pot-limit and fixed-limit; three hands per configuration; table seed 159; independent driver RNG seed `512 + seat`; raise cap 3. At every state, all three candidates were queried, then an independent driver action advanced the engine. Assertions checked action membership, integer raise bounds, table chip conservation and coverage of preflop/flop/turn/river. `sys.settrace` observed Floorfix exceptions without modifying candidate files.

Observed: **324 legal decisions for each of three candidates (972 total), all four streets, zero traced candidate `Exception` instances**. This probe was in-process and intentionally small to avoid interfering with the orchestrator's subprocess timing work. The probe's first diagnostic attempt and corrected repeat are described above.

The final helper's process-state correction was reviewed after those checks. It changes smoke reporting, not candidate code. Full-round timing was deliberately left to the orchestrator to run sequentially.

## Exact reviewed candidate hashes

| File | SHA-256 |
|---|---|
| `candidates/imported/fullhouse_floorfix.py` | `8d41454d6cafc10225ee474f807b9612dea8a73bd849dbf2ffd0d63a7c66c516` |
| `candidates/imported/fullhouse_shark.py` | `2d9aed30b745d398e27ab8ac5049781c1530fab1392623d8a7189d0598b69fb3` |
| `candidates/imported/vivelev_monte_carlo.py` | `dc79942d2be13a3d6bb10cc4824ca15f61f1ae473da6d758372b5b04cd00a8d3` |

Revised smoke-helper SHA-256 at re-review: `8f4da112136cc3fbe59c39f93a03c3364194d698021c1d27a8b58864ff7af57d`.

## Mutation-check scope

No authorization, credential, payment, destructive-write or sandbox boundary was changed. Candidate legal-action mapping was treated as ordinary domain correctness and exercised with real engine states and boundary regressions. Safety-guard mutation testing is **not applicable** to this B batch. No mutation tests were claimed or run.

This review authorizes no merge, deployment or submission. It establishes a reviewed research intake, with target runtime and competitive selection still open.
