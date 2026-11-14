# Claude handover: parallel B candidate discovery

You are Claude, working alongside GPT on Imperial AI Hack Pokerbots. **Keep B moving immediately:** read the existing registry, then search and inspect sources. GPT continues implementation and verification while you discover additional candidates; this handover does not pause GPT.

## Goal, people and constraints

The team collects reusable public poker policies, adapts them to the official format, and compares them in a controlled arena. Only after evaluation selects promising candidates does C improve them. There is no selected winner yet.

| Lane | Owner | Responsibility |
|---|---|---|
| A | Josh | Arena, integration and submission/release |
| B | Nguyen Anh, with GPT and Claude | Public-source discovery, provenance and compatible adapters |
| C | Nguyen Anh, later | Improve candidates selected by measured evaluation |
| D | Owen and Colin | Tournament design, comparisons and strategy findings |

- Rules: https://imperialaihack.com/pokerbots
- Repository: https://github.com/Josh-Lim18/fortnite-one-piece
- Target: 7/8-player no-limit Texas Hold'em; 2,000-chip/100BB stacks reset every hand; blinds 10/20.
- Submission: one Python 3.12 standard-library file, class `Agent`, at most 200KB; use 200,000 bytes conservatively.
- Timing: 10ms/action **including communication**, 10 seconds total thinking per 1,000-hand round.
- Actions use total **raise-to** amounts and supplied legal bounds. Nonfolded zero-stack players remain all-in opponents. The engine can also expose pot-limit/fixed-limit and raise caps.

## Workspace and ownership

Use the provided fortnite-one-piece project root; every repository path below is relative to it.

GPT's current local working folder is a downloaded snapshot **without .git**, based on main `bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d`. Do not overwrite it, initialize it as a replacement repository, or clone into this existing folder. If using an actual separate checkout, proposed branch: `research/claude-bot-discovery`; otherwise use the owned folders directly.

Read `AGENTS.md` and the agent board read-only when accessible. The user's direct B assignment supersedes the stale “everything Josh” ownership table for this agreed B scope. Do not post external messages, request ownership reassignment, modify permissions, or wait for routine-work approval.

**Claude initially owns only `research/claude/**`.** Create:

- `INTAKE.md`: ranked findings and clear rejections.
- `INTAKE.json`: structured source records.
- `STATUS.md`: progress, blockers and next actions.
- `CLAIMS.json`: source URLs/policy families currently being investigated, owner, status and updated timestamp to avoid duplicate effort.

GPT retains the existing five adapters, tests, shared registry/manifest, integration and GitHub work. Do not edit existing candidate files, `research/SHORTLIST.md`, `research/SOURCES.json`, `research/manifest.json`, root configuration, arena or release files. After intake agreement, optional adapters may use only `candidates/imported/claude_*.py` and `research/claude/checks/`.

B's delivery branch is `research/b-public-candidates`. The five candidate files are pinned by commit `f83822840c54cd283e62db1e7c8876a3539844bb`; subsequent commits carry checks, sources, run evidence and research documentation. GPT's local snapshot still has no .git. Read the branch and its PR status before integration; a feature-branch delivery does not imply a merge or tournament submission.

## What already exists

Read `research/SHORTLIST.md`, `research/SOURCES.json`, candidate notes, review reports and current run reports first. Eleven unique repositories already inspected:

`txnujk09/fullhouse-poker-bot`, `mbatv/fullhouse-engine`, `VIVelev/PokerBot-AI`, `nucats-soc/NUCATS-Pokerbot`, `devfun-org/poker-arena-starter-kit`, `advitrocks9/fullhouse-bot`, `EricSteinberger/PokerRL`, `EricSteinberger/Deep-CFR`, `fedden/poker_ai`, `datamllab/rlcard`, `conorarmstrong/noregrets`.

Do not count these as new leads. Earlier references labelled G5, Vikknows and gonfdcg are **not cleared candidates**; their exact repositories, policies and reuse scope must be established before inclusion.

Five standalone ports now exist in `candidates/imported/`: `fullhouse_floorfix.py`, `fullhouse_shark.py`, `vivelev_monte_carlo.py`, `nucats_starter.py`, `devfun_textured.py`. Research README and manifest now describe all five ports and distinguish current hashes from pre-cleanup reports. NUCATS is 5,682B (bd01e82f89ccb408523e96e6e9940c06b16202b71882091c6bd7346c9b09a298); Textured is 11,098B (88af4ca6c6962c6590a2beed68a4df5ca6143d95aa2131bec16ea3f762208b74).

Validation: **48 tests passed on actual Python 3.12.10 Windows**; final log: research/runs/unit-tests-python312-final.txt. Interpreter: `..\kit-review-helpers\python31210\python.exe`. Official kit: `..\kit-review-helpers\official-kit\imperial-ai-hack-pokerbots-kit`; inspect `bot.py`, `README.md`, `engine/` and `local_sim.py` for contracts.

Timing evidence in `research/runs/`:

| Report | Observed timeouts |
|---|---|
| `python312-8-1501.json` | VIVelev 1; Textured 1 |
| `python312-8-1501-final.json` | Floorfix 1; other four 0 |
| `python312-7-1502-final.json` | All five 0 |

The initial report predates NUCATS/Textured cleanup; both final reports match all five current files. All candidates in these reports had zero errors, invalid actions and bank exhaustion. Retain failures; the cause is not proven to be OS jitter. Platform-container validation remains pending. These runs do not establish competitive strength.

D handoff: [PR #4](https://github.com/Josh-Lim18/fortnite-one-piece/pull/4) proposes tests/check_submission.py and evaluation/ tooling with paired seeds, verdicts and six benchmark opponents; do not assume it is merged. It requires unchanged kit/ or --kit PATH. At inspected revision 033851cf22f086267c5ac6defce46a14748d5528 the gate allows <=1% timeouts, uses a 5s bank threshold and requires zero errors. Our five ports passed this local gate over 20,000 hands (four formats each), with one NUCATS fixed-limit timeout (0.03%) and zero errors/bank-outs. See research/runs/d-pr4-gate-python312.json and research/D_GATE_INTEGRATION.md. This is not zero-timeout or platform proof; Owen's own results remain unverified. Colin evaluates Owen's native poker/bot candidate, preserving independent evaluation.

## Your discovery mission

Find approximately **six credible new leads**, then shortlist about **three only if they qualify**. Prefer complete, compact NLHE policies with available code/assets, clear reuse licences and distinct strategies. Inspect actual decision code, not just README promises. A framework, evaluator or paper is not a complete bot. Do not pad the shortlist or imply famous champions are publicly available.

For each intake record capture:

`id, repository_url, revision, policy_paths, source_permalinks, license_expression, license_permalink, license_scope_code, license_scope_weights, game_variant, supported_players, complete_policy, asset_paths_and_sizes, dependencies, source_runtime_budget, expected_imperial_runtime, runtime_evidence_status, port_cost, competitive_claim, claim_source, evidence_type, limitations, policy_family, queue_status, queue_reason`.

Use immutable commit permalinks. Distinguish independently verified competition results, author-reported placements, local benchmarks and unsupported claims. Stars are discovery signals, not strength evidence. Check code and weights licensing separately; preserve notices. Unknown or missing assets/licences are explicit blockers. Expected runtime is an estimate until measured.

Perform static triage first. Do not execute unreviewed upstream modules, train models, or run heavy simulations. Coordinate compute with GPT before timing-sensitive work. Keep adaptation changes attributable; strategic tuning belongs to C.

**First handoff:** top three qualifying sources with exact policy/licence links, rejected leads with concrete reasons, and one recommended next port explaining feasibility, policy diversity and remaining risks. If fewer qualify, report fewer honestly.
