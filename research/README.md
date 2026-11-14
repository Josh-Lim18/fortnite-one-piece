# B handoff: five public-policy adapters

Five standalone candidates are ready for A/D research evaluation. The registry covers **11 unique repositories**, with source pins, licence scope and exclusions. **No winner has been selected.** C begins after meaningful target-format comparisons.

| Candidate in candidates/imported/ | Bytes | Role and retained limitation |
|---|---:|---|
| fullhouse_floorfix.py | 34,881 | Competition-derived equity/profile policy; stack-survival conservatism and only 24 postflop samples |
| fullhouse_shark.py | 3,684 | Deliberately weak control; source rank-order and absolute-seat flaws |
| vivelev_monte_carlo.py | 6,260 | Independent MC comparison; 32 samples, fixed thresholds, ties counted as full wins |
| nucats_starter.py | 5,682 | Made-hand/pot-odds control; board-made strength can trigger calls or raises |
| devfun_textured.py | 11,098 | Opening ranges and board texture; coarse postflop signal misses strong hands |

Each exports Agent, embeds its MIT notice, uses only the standard library and fits the conservative 200,000-byte ceiling. No shared module, model or runtime file is required. [manifest.json](manifest.json) pins current hashes and the exact bytes tested by each report.

## Evidence and remaining limits

**48 focused tests passed on actual Python 3.12.10 Windows**: [final log](runs/unit-tests-python312-final.txt). Coverage includes independent evaluators, source-policy differentials, thresholds, legal raise-to bounds, all-in opponents, history, positions and official-engine states. Independent reviews: [initial batch](REVIEW_B.md) and [expansion](REVIEW_B_EXPANSION.md). Historical reports retain their original runtime statements; current evidence is summarized here.

Each table below used the unchanged official engine, 1,000 hands, 2,000-chip stack resets, blinds 10/20, 10ms including IPC and a 10s bank:

| Python 3.12 report | File correspondence | Candidate timeouts |
|---|---|---|
| [Initial eight seats, seed 1501](runs/python312-8-1501.json) | NUCATS/Textured before cleanup; other three current | VIVelev 1; Textured 1 |
| [Final eight seats, seed 1501](runs/python312-8-1501-final.json) | All five current hashes | Floorfix 1; other four 0 |
| [Final seven seats, seed 1502](runs/python312-7-1502-final.json) | All five current hashes | All five 0 |

All candidates in those reports had zero errors, invalid actions and bank exhaustion. **There is no blanket reliability pass.** Failures are retained; their cause is not established. The seven-seat report also records two house calling-station timeouts. Earlier smoke-*-140*.json files and unit-tests.txt remain historical Python 3.14 evidence for the initial three candidates.

**D's separate local gate passed for all five current candidates:** [report](runs/d-pr4-gate-python312.json), [method/provenance](D_GATE_INTEGRATION.md). Serial execution on Python 3.12.10 covered four formats x 1,000 hands per candidate, **20,000 hands total**. All five exited 0 under D's <=1% timeout / <=5s thinking thresholds. NUCATS fixed-limit recorded one timeout (0.03%); every other round recorded none, with zero errors and bank-outs across all 20 rounds. This does not erase earlier failures or satisfy our zero-timeout smoke gate.

Local Python 3.12 execution is verified; the organizer's sealed platform is not. Fixed seats, few seeds, weak opponents and no uncertainty estimates make smoke scores unsuitable for selecting a winner. No platform submission is claimed.

## Reproduce checks

Extract the official kit from the [event page](https://imperialaihack.com/pokerbots), keep it unchanged, and set POKERBOTS_KIT to the directory containing engine/ and local_sim.py. Run from the repository root with Python 3.12.

```powershell
$env:POKERBOTS_KIT = '../kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit'
python -m unittest discover -s research/checks -p 'test_*.py' -v
python research/checks/smoke_candidates.py --kit $env:POKERBOTS_KIT --players 8 --seed 1503 --out research/runs/local-8-1503.json candidates/imported/fullhouse_floorfix.py candidates/imported/fullhouse_shark.py candidates/imported/vivelev_monte_carlo.py candidates/imported/nucats_starter.py candidates/imported/devfun_textured.py
```

The recorded local interpreter is ../kit-review-helpers/python31210/python.exe; substitute your installed Python 3.12. On macOS/Linux, set the equivalent environment variable and use python3.

Run timing checks sequentially with fresh output filenames; the helper refuses to overwrite evidence. Our intake helper exits nonzero for any candidate timeout, error, bank exhaustion, invalid action or process-health failure. It is not the arena scheduler or D's separate acceptance gate.

## Team handoff

**Josh (A):** import all five files with exact manifest hashes. Keep the engine unchanged. These ports do not modify arena, release or shared root configuration.

**Owen and Colin (D):** [PR #4](https://github.com/Josh-Lim18/fortnite-one-piece/pull/4) proposes tests/check_submission.py, an evaluation/ paired-seed runner, verdicts and six benchmark opponents. It expects unchanged kit/ or --kit PATH; do not assume it is merged. Inspected revision 033851cf22f086267c5ac6defce46a14748d5528 allows a timeout rate up to 1%, uses a 5-second bank threshold, and requires zero errors. Our five pinned ports passed that gate in the separate integration report above. Owen's own candidate results were not verified here. Colin evaluates Owen's native poker/bot candidate. Use balanced seats, varied/held-out opponents, multiple rounds and uncertainty; verify reproducible common deals before calling comparisons paired.

**Nguyen Anh (B/C):** all five initial ports are built. GPT retains them, shared registries, testing and integration. Claude searches for net-new policies under [CLAUDE_HANDOVER.md](CLAUDE_HANDOVER.md), initially owning research/claude/. Preserve imported parents; start attributable C variants only after evaluation.

## Records and delivery

- [SHORTLIST.md](SHORTLIST.md) and [SOURCES.json](SOURCES.json): source evidence, queue and exclusions.
- Adaptation records: [Floorfix](floorfix_notes.md), [Shark](shark_notes.md), [VIVelev](vivelev_notes.md), [NUCATS](nucats_notes.md), [Textured](textured_notes.md).
- sources/: preserved originals/licences, not submissions.
- build_floorfix.py: optional offline rebuild; the standalone candidate is already built.

Local work began from a downloaded snapshot of main bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d without .git. The delivery branch is research/b-public-candidates. Candidate bytes are pinned by commit f83822840c54cd283e62db1e7c8876a3539844bb; subsequent commits contain checks, sources, run evidence and research documentation. Consult the branch and its PR status before integration. A feature-branch delivery does not imply a merge or tournament upload.
