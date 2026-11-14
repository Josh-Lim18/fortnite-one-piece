# B: public candidate intake and adaptation

Base main revision: bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d.

A (Josh) owns arena/release; B (Nguyen Anh with GPT/Claude) owns intake; D (Owen and Colin) evaluates; C (Nguyen Anh) improves selected candidates later. No winner is selected.

- [x] Inspect 11 unique repositories; record source pins, licences, evidence strength and exclusions.
- [x] Preserve source/notices and build five standalone stdlib ports: Floorfix, Shark, VIVelev, NUCATS and Textured.
- [x] Independently review both batches; remove unused helpers/obsolete prose without strategy tuning.
- [x] Run 48 focused tests on actual Python 3.12.10 Windows; evidence: research/runs/unit-tests-python312-final.txt.
- [x] Run 1,000-hand subprocess rounds with unchanged official engine, default 10ms/10s limits and exact hashes.
- [x] Run D PR #4's behavior-unchanged gate serially: all five passed across four formats (20,000 hands); preserve the NUCATS fixed-limit timeout and distinguish D's tolerance from zero-timeout checks.
- [x] Reconcile manifest, notes and queue to all five current files.
- [x] Establish Claude's parallel discovery scope in research/CLAUDE_HANDOVER.md.
- [ ] Investigate timing failures and broaden repeated checks; observations are not a blanket reliability pass.
- [ ] Verify the organizer's sealed platform and conduct balanced multi-round D comparisons.
- [ ] Select candidates from target-format evidence before C improvements.

Constraints: 7/8-player NLHE; 2,000-chip/100BB resets each hand; blinds 10/20; one Python 3.12 stdlib file at most 200KB; 10ms including communication and a 10-second bank per 1,000 hands.

Initial eight-seat Python 3.12 report: VIVelev 1 timeout, Textured 1 timeout; NUCATS/Textured there predate cleanup. Final matching-file eight-seat report: Floorfix 1 timeout, other four 0. Final seven-seat report: all candidates 0. All candidates in those reports had zero errors, invalid actions and bank exhaustion. Retain every report and do not assign an unproven OS/IPC cause. Platform and strength remain pending.

D tooling is proposed in [PR #4](https://github.com/Josh-Lim18/fortnite-one-piece/pull/4), not asserted merged. At inspected revision 033851cf22f086267c5ac6defce46a14748d5528, its gate allows <=1% timeouts, uses a 5s bank threshold and requires zero errors. Our five pinned ports passed the local gate, recorded in research/runs/d-pr4-gate-python312.json: NUCATS had one fixed-limit timeout (0.03%), all other rounds zero; all 20 rounds had zero errors and bank-outs. This is not sealed-platform proof or our zero-timeout gate. Owen's own candidate results remain unverified. Colin evaluates Owen's native poker/bot candidate.

GPT owns existing ports, shared registries, verification and integration. Claude owns research/claude/** for new discovery/static triage initially; optional future adapters require agreed intake and separate claude_* paths. Feature branch research/b-public-candidates is being populated by the coordinator; the local snapshot still lacks .git.

Review focus: raise-to bounds, all-in versus folded seats, ties/wheels/flushes, true positions, bounded compute/history, provenance and report-to-file hash correspondence.
