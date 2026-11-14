# Independent review: NUCATS and Textured expansion

Reviewed 2026-11-14 by the separate `review_b_expansion` agent. This reviewer did not implement either candidate. **No blocking source-port correctness defect remains. Both are suitable for A/D research intake; this is not approval of competitive strength or platform readiness.**

The initial pass read raw candidates, preserved upstream policies/helpers/licences, focused checks and the official kit's state/action contract before reading builder notes. Comments remained visible. The local working tree is a downloaded snapshot, not a Git checkout; the supplied remote baseline is `bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d`. Exact reviewed bytes are pinned below rather than claiming a nonexistent final commit SHA.

## Findings and resolution

1. **Resolved, low impact: obsolete Textured usage/performance docstring.** The first candidate included source instructions for `./pokerkit` and `examples/agent.py`, plus an unverified bb/100-lift statement. Those did not describe the Imperial standalone adapter. The coordinator removed the redundant source docstring while preserving provenance, MIT notice and policy code. The unchanged original remains under `research/sources/`.
2. **Resolved, low impact: unused NUCATS display helpers.** The first candidate carried `card_name`, `describe_hand` and their name tables even though decisions never called them. The coordinator removed those helpers/constants and adjusted the hand-type docstring. The scoring and decision functions remain unchanged; focused source differentials still pass.
3. **No hidden exception observed in valid-state coverage.** Textured catches several exception types and could otherwise silently fold if its mapping broke. A trace of the final files during official generated-state checks observed zero candidate `Exception` instances. NUCATS has no broad exception fallback. Finite coverage does not prove all possible states correct.
4. **Timing evidence must retain failures.** The initial Python 3.12 eight-seat report, `runs/python312-8-1501.json`, records a VIVelev timeout and a Textured timeout. It must not be described as an all-pass run or discarded in favor of later successful runs. A scheduler/IPC explanation is plausible but not established by that report alone. The coordinator owns further sequential timing checks and their interpretation.

No behavioral strategy repair was requested by this review. NUCATS' board-made hand strength and Textured's pair-with-board-only decision signal remain intentionally weak source policies.

## Criteria

| Criterion | Status | Evidence and limit |
|---|---|---|
| Standalone `Agent`, size and dependencies | PASS | Final NUCATS is 5,682 bytes and imports `collections`; Textured is 11,098 bytes and imports `typing`. No runtime file access, network, process launch, model loading or expensive import work found. |
| Actual Python 3.12 execution | PASS, local Windows | Reviewer executed both focused suites with the isolated Python 3.12.10 interpreter, not just a grammar parser. This does not reproduce the organizer's Linux/container environment. |
| Total raise-to amounts and legal bounds | PASS for tested states | NUCATS uses `min(3 * minimum, maximum)` only when raising is available. Textured maps the source's total-commitment contract and clamps to official bounds. Fixed-limit, pot-limit, short all-in and unavailable-raise cases are checked. |
| Seven/eight-player tables and all streets | PASS for tested states | NUCATS tests exercise 42 isolated official betting phases. Textured tests exercise 2,108 actual states across both table sizes and all three betting structures, including 301 all-in bounds and 756 closed-raising states. |
| Source-policy fidelity | PASS with documented adaptations | NUCATS preserves thresholds and strength semantics. Textured preserves ranges, sizing and coarse postflop logic; removal of the two-second gate, true button mapping and blind-facing opening recognition are disclosed adaptations. Source-action comparisons cover 1,200 NUCATS cases and 4,610 Textured cases. |
| Position mapping | PASS, target 7/8 seats | Textured tests all 149 six/seven/eight-seat button/seat combinations. Additional early seats receive the source UTG range. NUCATS intentionally adds no position model. |
| All-in and closed-raising handling | PASS | Official zero-stack live-opponent, capped-call, short-raise non-reopening and free-check states remain legal. Neither policy pretends to calculate opponent-conditioned equity. |
| State isolation | PASS by inspection and checks | Both agents are stateless. NUCATS differential checks assert that input state is not mutated; Textured constructs new mapping lists/dictionaries and does not mutate its policy tables. |
| Attribution and licences | PASS | Full MIT notices are preserved in each candidate and source files. NUCATS tests confirm original Git blob hashes. Textured's source contract excerpt explicitly identifies raise-to amounts and its pinned source. |
| Tests meaningfully cover behavior | PASS | Source differential checks, exact thresholds, all-in limits, actual engine-generated states and inherited strategy defects are checked. Coverage goes beyond compilation or imitation of one implementation path. |
| 10ms decisions / 10s bank | UNVERIFIED by this review | Reviewer did not run full subprocess timing jobs. Initial integration report contains timeouts. Use coordinator-owned reports for subsequent observations; local success cannot certify the sealed platform. |
| Competitive strength / winner selection | UNVERIFIED | These are distinct public reference policies, not measured tournament winners. Repeated seats, seeds, opponent pools and held-out evaluation remain necessary. |

## Commands and observed results

From the repository root, using `../kit-review-helpers/python31210/python.exe`:

```text
python research/checks/test_nucats.py
python research/checks/test_textured.py
```

Reviewer observed **11/11 NUCATS tests pass in 0.092s** and **10/10 Textured tests pass in 0.145s** on Python 3.12.10 before cleanup. The coordinator repeated both suites after cleanup and reported 21 passing tests. The reviewer independently re-read the cleanup and then reran the final bytes' four actual-state integration tests with exception tracing: **4/4 passed in 0.261s**, with zero traced candidate exceptions.

The ephemeral trace loaded the two test modules, ran NUCATS' three `OfficialStateTests` and Textured's `test_actual_official_states_all_structures_and_short_stacks`, and used `sys.settrace` to collect only `Exception` subclasses raised from the two candidate file paths. It restored tracing in `finally`; it did not modify candidate code. These short in-process tests are not latency evidence and were performed while the coordinator's full-round timing work was paused.

## Exact reviewed final files

| File | Bytes | SHA-256 |
|---|---:|---|
| `candidates/imported/nucats_starter.py` | 5,682 | `bd01e82f89ccb408523e96e6e9940c06b16202b71882091c6bd7346c9b09a298` |
| `candidates/imported/devfun_textured.py` | 11,098 | `88af4ca6c6962c6590a2beed68a4df5ca6143d95aa2131bec16ea3f762208b74` |

The report covers these exact candidate bytes. Later policy edits need renewed checks and review.

## Mutation-check scope

No authorization, credential, payment, destructive-write or sandbox boundary was changed. Legal-action mapping is ordinary game-domain correctness and has boundary/generated-state tests. Safety-guard mutation testing is **not applicable**; no mutation tests were claimed or run.

This review authorizes no merge, deployment or tournament submission. It records reviewed source ports with remaining timing/platform and competitive-evaluation limits.
