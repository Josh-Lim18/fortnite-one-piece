# B public-bot shortlist

Source evidence scan: **2026-11-14**. This is an intake order, not a strength leaderboard. Rank by port feasibility, distinct policy families, game compatibility and evidence quality. Stars and self-reported win rates do not establish strength under Imperial rules.

Target: 7/8-player no-limit Hold'em; 2,000 chips (100BB) reset each hand; blinds 10/20; one Python 3.12 standard-library `bot.py` no larger than 200KB; 10ms per decision including communication and 10 seconds of thinking per 1,000-hand round. Use a conservative 200,000-byte local ceiling.

**Five standalone ports are now built and reviewed.** Actual Python 3.12.10 Windows execution passed 48 focused tests; full-round reports include timeouts and do not establish blanket reliability or competitive strength. Exact current hashes and retained failures are in [manifest.json](manifest.json). Sealed-platform validation and winner selection remain pending; C is later.

## Initial intake

| Order | Source / policy | Queue | Why include it | Main adaptation cost |
|---|---|---|---|---|
| 1 | Fullhouse **floorfix** | Adapted; evaluation pending | Compact actual competitor; equity, pot odds and opponent profiling | Replace eval7/import-time MC, reduce compute, map 7/8 seats and reset stacks |
| 2 | Fullhouse **Shark** | Adapted; weak control | Very small public reference; cheap-call and positional pressure family | Interface, chip/action semantics and legal-action handling |
| 3 | VIVelev **MonteCarloBot** | Adapted; evaluation pending | Independent MC policy; separates equity estimation from Floorfix's richer rules | PyPokerEngine replacement, bounded samples and state mapping |
| 4 | **NUCATS starter** | Adapted; evaluation pending | Eight-seat source; cheap made-hand baseline | Inline helper and map state/actions |
| 5 | dev.fun **Textured** | Adapted; evaluation pending | Opening-range charts and board-texture sizing | Deadline guard, actual position and blind-facing opening behavior |
| 6 | Advit **Deep CFR** | Blocked from initial batch | Competitive author-reported result; useful later research comparator | Model size, NumPy/eval7, six-seat assumptions and asset-license scope |

There are six source candidates above. The framework exclusion list below has six entries and includes Advit again for its runtime/asset blockers: **11 unique repositories**, not 12.

### 1. Fullhouse floorfix

Revision: `4fe154318949aa60430682416f148733c6f0d564`. [README](https://github.com/txnujk09/fullhouse-poker-bot/blob/4fe154318949aa60430682416f148733c6f0d564/README.md) · [final policy](https://github.com/txnujk09/fullhouse-poker-bot/blob/4fe154318949aa60430682416f148733c6f0d564/bots/floorfix/bot.py) · [MIT license](https://github.com/txnujk09/fullhouse-poker-bot/blob/4fe154318949aa60430682416f148733c6f0d564/LICENSE)

- Complete 28,701-byte six-player no-limit agent, originally for 400-hand persistent-stack Fullhouse matches. The final `floorfix` is the submitted policy named in the README; `mybot` omits pocket-pair preflop equity entries. Do not silently substitute the buggy baseline.
- MIT © 2026 Tanuj Kakumani covers authored bots, training and harness code; preserve the notice. The external Fullhouse engine is not redistributed by this repository.
- Source imports `eval7`, constructs a 169-class preflop table using Monte Carlo at import, and budgets 0.45s soft / 0.90s hard per action. Floorfix itself needs no external model. The separate unshipped CFR variant needs an uncommitted approximately 38MB blueprint.
- Author reports top64 in the qualifier. Approximately 98.6% wins and +25.5k mean chip delta describe a weak reference pool, not the tournament field. No independent official placement was verified.
- A B port must record changes to evaluator, table generation, chip units, persistence, interface and compute. Source survival/stack-protection assumptions are a known mismatch with per-hand resets; strategy tuning should remain separately attributable.

### 2. Fullhouse Shark

Revision: `a80b26957db5f5515d9273a15d1b73aadf8985db`. [README](https://github.com/mbatv/fullhouse-engine/blob/a80b26957db5f5515d9273a15d1b73aadf8985db/README.md) · [policy](https://github.com/mbatv/fullhouse-engine/blob/a80b26957db5f5515d9273a15d1b73aadf8985db/bots/shark.py) · [MIT license](https://github.com/mbatv/fullhouse-engine/blob/a80b26957db5f5515d9273a15d1b73aadf8985db/LICENSE)

- A bundled reference opponent, **not a winning competition submission**. Upstream policy is approximately 1.9KB and imports only `random`; no model or data.
- MIT © 2026 Fullhouse Hackathon. The engine is a framework; the specific bundled Shark policy is what enters the candidate pool.
- Known source limitations: lexical rank sorting misclassifies some intended premium holdings; seat index is used as a positional proxy; postflop logic ignores hand strength. Preserve or explicitly label repairs rather than calling a changed policy a faithful port.
- Low port effort makes it useful for contract checks and a lower strength control. Low complexity is not measured proof of 10ms compliance.

### 3. VIVelev MonteCarloBot

Revision: `c1be1110b258fef0dedda91c28e8c2634b9e778c`. [README](https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/README.md) · [policy](https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/src/bots/monte_carlo.py) · [dependencies](https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/requirements.txt) · [MIT license](https://github.com/VIVelev/PokerBot-AI/blob/c1be1110b258fef0dedda91c28e8c2634b9e778c/LICENSE)

- Complete 3,835-byte PyPokerEngine policy with no learned assets. The README documents local play; no competition placement was found. MIT © 2018 Victor Velev.
- Simulates 1,000 random runouts per action against the configured number of players. Repository requirements include NumPy and PyPokerGUI, but the policy itself primarily depends on PyPokerEngine's evaluator/card helpers/interface.
- Distinct policy family: fixed win-rate thresholds above 0.5/0.75/0.85 choose fold/call/min-raise/max-raise. An adapter needs a stdlib evaluator and a tightly bounded sample budget.
- Known source flaws: ties count as full wins; initial player count is retained after folds; fixed thresholds are overly tight in multiway pots; raising is assumed available. Distinguish faithful-policy limitations from explicit correctness fixes.

### 4. NUCATS starter

Revision: `67cadea4486039ef279c6e4718e3b90d58134939`. [README](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/README.md) · [policy](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/bots/my_bot.py) · [card helper](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/bots/pokerbot/cards.py) · [MIT license](https://github.com/nucats-soc/NUCATS-Pokerbot/blob/67cadea4486039ef279c6e4718e3b90d58134939/LICENSE)

- Source supports up to **eight** NLHE bots, 1,000 starting chips, 10/20 blinds, 20 hands and 5s/action. It is an educational starter, with no verified competitive ranking.
- MIT © 2026 NUCATS. Policy 3,234B plus card helper 3,890B; the helper uses only `collections.Counter`. No model or data assets; flattening avoids the socket client/framework.
- Raises high pocket pairs preflop and high made-hand scores postflop; otherwise checks free, calls strength ≥0.3 or pot odds ≤0.2, and folds.
- Useful as a separate made-hand control, not a strong candidate claim. Board-only pairs can inflate strength; kickers, opponent ranges and number of live opponents are ignored. Source comment says three-of-a-kind while the actual 0.7 threshold also includes two pair.

### 5. dev.fun Textured

Revision: `fc19bb25e9c6e8fabc26099d6a767241fc99fc2f`. [README](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/README.md) · [policy](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/assets/decide_textured.py) · [MIT license](https://github.com/devfun-org/poker-arena-starter-kit/blob/fc19bb25e9c6e8fabc26099d6a767241fc99fc2f/LICENSE)

- Self-contained 6,727-byte policy with only `typing` import, opening-range sets for six positions and board-texture sizing tables. MIT © 2026 dev.fun. No external model.
- Repository describes evaluation against five reference opponents. Its general benchmark/learning claims are not verified results for this policy.
- Required adapter changes: remove the `deadline_s < 2` guard (a 10ms argument would always check/fold); derive true button-relative 7/8-seat positions instead of fixed seat numbers; reconcile the source `call_chips == 0` opening condition with facing blinds.
- Postflop only checks whether a hole rank pairs the board, so overpairs, straights and flushes can be missed. This is a chart/texture control; do not describe the signal as actual equity.

### 6. Advit Deep CFR — blocked

Revision: `e504793d480b1b975f25258d25939b45c6dbd5a4`. [README](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/README.md) · [runtime](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/bot.py) · [inference](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/deep_cfr_lookup.py) · [features](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bot/features.py) · [license](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/LICENSE)

- A real submitted six-player agent. Author reports 12th of 500+ qualifier entrants and 15th of 64 finalists. The repository has a leaderboard screenshot; this remains author-supplied evidence, not independently verified official results. Local +22.41 bb/100 and +19.89 held-out scores are explicitly separate benchmark results.
- Runtime uses NumPy and eval7. The committed [model](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/data/deep_cfr_model.npz) is **590,758B**, already above the whole-file cap; a preflop equity asset is also required. Source used 2s/action. A six-position tuple can index out of range at seven/eight seats.
- MIT notice enumerates `bot/`, `training/`, `tooling/`, `scripts/`, `tests/`, `docs/`; it excludes the vendored engine and omits `bots/` and `data/`. Do not clear model or opponent-pool redistribution merely because repository metadata says MIT. [Opponent-pool description](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/bots/README.md) confirms these are benchmark opponents, not the submission.
- Defer source distillation/compression or retraining to a separate justified effort. It is not a quick standard-library port.

## Framework and heavyweight exclusions

These are research leads, not imported policies. Exact pins and source evidence are also in [SOURCES.json](SOURCES.json). Framework source checks were performed by the separate framework research agent.

| Source | Revision | Actual deliverable and license | Why exclude from the first arena batch |
|---|---|---|---|
| [PokerRL](https://github.com/EricSteinberger/PokerRL/blob/e02ea667061b96912e424231da071b6f20a262f7/README.md) | `e02ea667061b96912e424231da071b6f20a262f7` | Research infrastructure; [MIT](https://github.com/EricSteinberger/PokerRL/blob/e02ea667061b96912e424231da071b6f20a262f7/LICENSE); [abstract evaluation agent](https://github.com/EricSteinberger/PokerRL/blob/e02ea667061b96912e424231da071b6f20a262f7/PokerRL/rl/base_cls/EvalAgentBase.py) | Legacy Python3.6/PyTorch0.4.1 and compiled C++ components; no ready transferable 7/8-player NLHE policy established |
| [Deep-CFR](https://github.com/EricSteinberger/Deep-CFR/blob/2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5/README.md) | `2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5` | Deep CFR/SD-CFR implementation; [MIT](https://github.com/EricSteinberger/Deep-CFR/blob/2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5/LICENSE); [runtime](https://github.com/EricSteinberger/Deep-CFR/blob/2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5/DeepCFR/EvalAgentDeepCFR.py) | Checkpoints **exist**, but FHP examples differ from target: [average](https://github.com/EricSteinberger/Deep-CFR/blob/2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5/trained_agents/Example_FHP_AVRG_NET.pkl) 869,414B; [single](https://github.com/EricSteinberger/Deep-CFR/blob/2e664ebbe5bf3c8f8ab56057205cbe4c2c7baeb5/trained_agents/Example_FHP_SINGLE.pkl) 81,188,437B. PokerRL/NumPy/PyTorch dependencies |
| [fedden/poker_ai](https://github.com/fedden/poker_ai/blob/73fb394b26623c897459ffa3e66d7a5cb47e9962/README.md) | `73fb394b26623c897459ffa3e66d7a5cb47e9962` | Archived Pluribus-inspired simplified 20-card research; actual [GPLv3 license](https://github.com/fedden/poker_ai/blob/73fb394b26623c897459ffa3e66d7a5cb47e9962/LICENSE), despite API NOASSERTION | Wrong game abstraction; [SciPy/sklearn/NumPy/dill dependencies](https://github.com/fedden/poker_ai/blob/73fb394b26623c897459ffa3e66d7a5cb47e9962/requirements.txt); not the released original Pluribus bot |
| [RLCard](https://github.com/datamllab/rlcard/blob/d7d0a957baf4cc7225a50522adb0164bf130a9d0/README.md) | `d7d0a957baf4cc7225a50522adb0164bf130a9d0` | Card-game framework; [MIT](https://github.com/datamllab/rlcard/blob/d7d0a957baf4cc7225a50522adb0164bf130a9d0/LICENSE); [model registry](https://github.com/datamllab/rlcard/blob/d7d0a957baf4cc7225a50522adb0164bf130a9d0/rlcard/models/__init__.py) | No ready pretrained NLHE policy in inspected registry. Leduc checkpoint and [limit-Hold'em rule model](https://github.com/datamllab/rlcard/blob/d7d0a957baf4cc7225a50522adb0164bf130a9d0/rlcard/models/limitholdem_rule_models.py) are different games |
| [noregrets](https://github.com/conorarmstrong/noregrets/blob/757f7692738069522195d2b486eec60a8b010c0c/README.md) | `757f7692738069522195d2b486eec60a8b010c0c` | Rust Pluribus-style 2–6-player implementation; [MIT source](https://github.com/conorarmstrong/noregrets/blob/757f7692738069522195d2b486eec60a8b010c0c/LICENSE) | README says trained artifacts were never public; commercial artifacts separate. Approximately 2,000ms default resolving budget, wrong runtime and seat limit |
| [Advit Deep CFR](https://github.com/advitrocks9/fullhouse-bot/blob/e504793d480b1b975f25258d25939b45c6dbd5a4/README.md) | `e504793d480b1b975f25258d25939b45c6dbd5a4` | Actual six-player submitted agent; scoped MIT code | Already discussed above: model >200KB, NumPy/eval7 and unresolved checkpoint/opponent-pool licensing scope |

No exclusion is a claim that the underlying research is weak. These sources fail the immediate packaging, runtime, game-format or ready-policy requirements.

## Next queue and handoff

1. The five ports (Floorfix, Shark, VIVelev, NUCATS and Textured) are built. Use the exact files and hashes in [manifest.json](manifest.json); do not schedule NUCATS or Textured as new adaptations.
2. Actual Python 3.12.10 Windows tests passed. Initial eight-seat timing recorded VIVelev and Textured timeouts; final eight-seat bytes recorded one Floorfix timeout; final seven-seat bytes recorded none for the candidates. Retain all reports, distinguish pre-cleanup file hashes, and investigate rather than assume the cause. Organizer-platform execution remains pending.
3. Claude's parallel discovery lane owns research/claude/ and seeks net-new complete policies under [CLAUDE_HANDOVER.md](CLAUDE_HANDOVER.md). Existing source candidates and heavyweight exclusions are not new leads.
4. D tooling is proposed in [PR #4](https://github.com/Josh-Lim18/fortnite-one-piece/pull/4), not assumed merged: submission checks, paired-seed evaluation, verdicts and six benchmark opponents. Keep the official kit unchanged. Inspected revision 033851cf22f086267c5ac6defce46a14748d5528 allows <=1% timeouts, a 5s bank threshold and zero errors; our five current ports passed that separate local gate across 20,000 hands (one NUCATS fixed-limit timeout, zero errors/bank-outs), recorded in [the D integration report](runs/d-pr4-gate-python312.json). Do not confuse this tolerance gate with our zero-timeout smoke helper or sealed-platform proof; Owen's own results remain unverified. Colin evaluates Owen's native poker/bot candidate.
5. Compare candidates with balanced seats, varied and held-out opponents, multiple rounds and uncertainty estimates. Verify paired-deal reproducibility. Select candidates from target-format evidence before C improvements.

Evidence scan: **2026-11-14**. Pins make source review reproducible; updates after those revisions are outside this audit.
