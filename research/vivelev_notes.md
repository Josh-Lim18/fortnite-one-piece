# VIVelev Monte Carlo: B adaptation record

**Integration update:** current full-round results, independent review and target-runtime limitations are in [the B handoff](README.md). Verification below records the adaptation-stage checks.

Candidate: `candidates/imported/vivelev_monte_carlo.py` (6,260 bytes).
Status: adapted and focused checks passed; tournament strength and official-runtime acceptance are not established. This is a research candidate, not a selected winner. C remains later.

## Provenance and reuse

- Repository: https://github.com/VIVelev/PokerBot-AI
- Exact revision: `c1be1110b258fef0dedda91c28e8c2634b9e778c`.
- Original policy: https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/src/bots/monte_carlo.py
- Original licence: https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/LICENSE
- MIT, copyright (c) 2018 Victor Velev. Complete notice retained in the submission file.
- Preserved original: `research/sources/vivelev_monte_carlo_upstream.py`, verified Git blob SHA-1 `a673e8ec80914782f0942b5d03aad96631485dd8`.
- Preserved licence: `research/sources/vivelev_LICENSE.txt`, verified Git blob SHA-1 `de0940ae8417d6c5f9a470f283e933924bfbeb69`.
- No upstream module was imported or executed. These originals are provenance files, not submissions.

The independent bitset hand evaluator was written for this project's B adapters and inlined from the Floorfix adaptation's evaluator. It does not copy the organizer's evaluator or import PyPokerEngine/eval7. Its card encoding uses ranks `23456789TJQKA` and suits `shdc`; higher packed scores win.

## Preserved strategy

Uniformly sample unseen community cards and opponent hole cards, compare best-five hands, then apply the original strict thresholds:

| Estimated probability | Upstream decision retained |
|---|---|
| At most 0.5 | Check for free; otherwise fold |
| Above 0.5 and at most 0.75 | Call (check if free) |
| Above 0.75 and at most 0.85 | Minimum legal raise |
| Above 0.85 | Maximum legal raise |

Tied best hands count as a full win, exactly as upstream's `my_score >= max(opponents_score)`. This is probability of an equal-best hand, not split-pot equity. There are no added pot-odds rules, position ranges, bluff logic, opponent learning or tuned strategy thresholds.

## Necessary adapter changes

1. **Interface and cards:** expose the organizer's `Agent.act(state)` and optional `on_table_start(info)`; consume rank-then-suit card strings and official `board`, `folded` and `legal_actions` fields. Return legal action dictionaries with total raise-to amounts.
2. **Dependencies:** replace PyPokerEngine card sampling and evaluation with standalone standard-library code. Imports are only `random` and `time`. No model files, filesystem reads, subprocesses, network, or import-time rollouts.
3. **Compute budget:** upstream performs 1,000 rollouts every decision. This adapter performs at most **32** with a **1.2ms wall-clock target**, stopping between complete rollouts. One rollout always completes. This changes estimate precision substantially and may change actions; it is explicitly a runtime adaptation. A slow rollout or scheduling pause can overrun that target, so only measured subprocess rounds can establish compliance with the 10ms/10s limits.
4. **Opponents:** upstream stores the initial table player count. This adapter samples one opponent for each currently nonfolded seat other than the acting seat. This explicit state-mapping change avoids treating folded players as live. A zero-stack seat remains an opponent when `folded[seat]` is false, so all-in hands remain in showdown comparisons. This is the one documented opponent-count deviation from upstream.
5. **Unavailable raises:** when the desired raise is illegal, call if facing a bet and otherwise check. Use the supplied minimum/maximum raise-to bounds directly, including short all-ins, fixed-limit bounds and raise caps. No source policy tuning is implied.
6. **Randomness:** use an Agent-owned seeded generator (`2018 + seat`) for reproducible sample sequences. The fixed maximum is deterministic; deadline-dependent early stopping can vary by machine load. Seeded tests disable that early deadline when checking repeatability.

All opponents remain uniform random unknown hands; neither their actions nor folded-card information is used to infer ranges. Side-pot-specific equity is not modeled. Those limitations are retained for D to measure and C to reconsider later.

## Verification

Command from repository root:

```powershell
python -B research/checks/test_vivelev.py
```

Observed result: **13 tests passed**, 2026-11-14, Python 3.14.

- 1,200 independently seeded 5-, 6- and 7-card differential comparisons against a slow combinations-based five-card oracle.
- Named category, wheel, two-trips full house, three-pair kicker, flush and board-tie cases.
- Original strict threshold boundary cases and unavailable-raise fallbacks.
- All-in opponent inclusion and folded-opponent exclusion.
- Independent seeded rollout repeatability, no duplicate/known-card draws, ties-as-full-wins and deadline stopping.
- Legal actions on official engine-generated states for 7 and 8 seats, no-limit/pot-limit/fixed-limit and a raise cap, spanning all four streets. Only 4 hands per configuration; these in-process probes do not measure tournament performance or IPC overhead.
- Single-file size, import restriction, attribution and Python 3.12 syntax parsing.

Subsequent integration: the combined 48-test suite passed on actual Python 3.12.10 (`runs/unit-tests-python312-final.txt`), and independent review is recorded in `REVIEW_B.md`. The first Python 3.12 eight-seat 1,000-hand report recorded one VIVelev timeout; subsequent final-byte seven- and eight-seat runs recorded none for this bot. All recorded zero errors, invalid actions and bank exhaustion. Preserve all three `runs/python312-*.json` reports. Organizer-platform timing and robust competitive strength remain unverified; no ranking or submission-readiness claim follows from these tests.
