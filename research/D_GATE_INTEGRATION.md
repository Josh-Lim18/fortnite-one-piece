# D PR #4 gate integration

All five current B adapters passed D's local submission gate on Python 3.12.10 Windows. This is a pass against D's tolerance thresholds, not a zero-timeout guarantee, competitive ranking, or sealed-platform approval.

## Method and provenance

The coordinator ran tests/check_submission.py from [D PR #4 revision 033851cf22f086267c5ac6defce46a14748d5528](https://github.com/Josh-Lim18/fortnite-one-piece/blob/033851cf22f086267c5ac6defce46a14748d5528/tests/check_submission.py) sequentially for all five candidates. This gate is not included in B's branch; obtain it from the pinned D revision without assuming PR #4 is merged. Its logic was unchanged.

From a checkout containing that gate, using Python 3.12 and the unchanged official kit:

```text
python tests/check_submission.py <candidate> --kit <kit> --hands 1000
```

Repeat serially for the five candidate paths in research/manifest.json. The gate runs no-limit, pot-limit, fixed-limit and no-limit with raise cap 3: 4 x 1,000 hands per candidate, 20,000 total. The runner uses 10ms/action and a 10s bank; the gate accepts at most 1% timeouts, at most 5s thinking per round, and zero errors.

The [raw report](runs/d-pr4-gate-python312.json) preserves each candidate hash, exit code, stdout and stderr. The manifest's separate d_gate_integration object pins that report's SHA-256, all five matching current-file hashes and parsed round observations. Earlier smoke failures remain intact.

Provenance precision: the local gate has **one additional terminal newline** from file materialization. Its local size is 6,222 bytes and SHA-256 is f3256ae001e6fef19bf3508ceddadf8cce3230bcc5dc44417a486fba2ccd3f0d. Removing only the final byte reproduces the exact upstream 6,221-byte Git blob a72ab2ffd091252abb7ebbb91fffa99c1e1dc8d0. The local gate is behavior-equivalent, not byte-identical to upstream.

## Observations

| Candidate | Four-format exit | Timeouts |
|---|---:|---|
| Floorfix | 0 | 0 |
| Shark | 0 | 0 |
| VIVelev | 0 | 0 |
| NUCATS | 0 | 1 in fixed-limit: 1/3,524 decisions, displayed 0.03% |
| Textured | 0 | 0 |

All 20 rounds recorded zero errors and bank-outs and passed D's thresholds. NUCATS' timeout is retained; its cause is not assigned. The prior VIVelev/Textured and Floorfix smoke timeouts also remain evidence.

Our smoke helper fails on any candidate timeout, so these gates answer different questions. Finite local passes do not prove platform readiness or robust competitive strength. No winner is selected. This verifies our five pinned B ports only; Owen's own candidate results remain unverified.
