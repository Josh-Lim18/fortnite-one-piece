# Fullhouse Floorfix: B candidate adaptation

**Integration update:** current full-round results, independent review and target-runtime limitations are in [the B handoff](README.md). Verification below records the adaptation-stage checks.

Status: standalone adapter implemented and local unit/differential checks passed. Ready for A/D's official-engine subprocess smoke and arena evaluation. No winning-performance claim is made. C's later changes to the selected winner are outside this port.

## Provenance and reproducibility

- Source: [`txnujk09/fullhouse-poker-bot`, `bots/floorfix/bot.py`](https://github.com/txnujk09/fullhouse-poker-bot/blob/4fe154318949aa60430682416f148733c6f0d564/bots/floorfix/bot.py).
- Pinned revision: `4fe154318949aa60430682416f148733c6f0d564`.
- Source preserved at `research/sources/fullhouse_floorfix.py`; SHA-256 `4cc3f54eb70d487d23e88241c5e2f096a40127c0f190db6e70a2e3dff62a9a56`.
- MIT, copyright 2026 Tanuj Kakumani. The full upstream notice, including its engine attribution paragraph, is included in the standalone adapter. The organizer's engine is not copied into it.
- Output: `candidates/imported/fullhouse_floorfix.py`, 34,881 bytes, SHA-256 `8d41454d6cafc10225ee474f807b9612dea8a73bd849dbf2ffd0d63a7c66c516`.
- Rebuild: `research/build_floorfix.py`. It reads only the preserved source/license and writes the candidate file. The upstream source was read before executing its extracted table-builder function.
- Team repository snapshot baseline: `bec6ca67f9076d6aa580de12ac2bf3f342cf9f8d`. This work changed only this note, the standalone candidate, its build script and `research/checks/test_floorfix.py`.

## What changed

1. Added the official `Agent`, `act(state)`, `on_table_start(info)` and `on_hand_end(summary)` interface. The official state is translated into the source policy's field names. Opponent IDs are stable strings such as `seat_0`, avoiding falsey seat-zero IDs.
2. Replaced the external `eval7` dependency with an independently implemented standard-library evaluator. Suit and repeated-rank bitsets produce a packed category/kicker score; higher wins. The small compatibility object preserves the upstream `Card`, `evaluate` and hand-type labels, including `Trips` and `Quads`.
3. Precomputed and embedded all 169 preflop classes using the source's 900 samples per class, deck order `shdc`, non-pair seed `12345` and independent pair seed `67890`. This retains the source's pocket-pair bugfix and removes expensive import-time simulation. The runtime needs no separate files.
4. Replaced the hardcoded 100-chip big blind with the official `state['big_blind']` in sizing, cheap-call and stack-depth calculations. At Imperial's 20-chip big blind, the original early-position 3BB opening raise is 60 chips.
5. Used the official button for positions, retaining the source's seat-distance definition of late position. Folded players are excluded from equity opponents; zero-stack all-in players who have not folded remain included.
6. Returned explicit total raise-to amounts clamped to the official `[min_raise_to, max_raise_to]`. Short all-in ranges are supported. A desired raise becomes call/check when raising is unavailable; the final interface also validates action legality.
7. Moved gameplay RNG and opponent counts into each `Agent`. Completed-hand history is aggregated once during `on_hand_end`; repeated/stale summaries are ignored. Decisions copy at most one row per seat and merge only the current hand's history, so there is no repeated whole-round scan. Table startup resets counts and RNG.
8. Reduced postflop Monte Carlo from hundreds/thousands of samples and a 450ms budget to at most **24 samples**, with a **1.5ms** deadline checked before every sample. One sample or OS scheduling can overrun this soft deadline. The obsolete source hard-budget branch, which never actually interrupted work, was removed. RNG seed is `0xC0FFEE + seat`; changing timing can change sample count and subsequent mixed decisions.

All preflop equity thresholds, stack-commitment thresholds, made-hand rules, draw rules, pot fractions, opponent classifications and bluff probabilities are retained. The Monte Carlo sample count is an execution-budget adaptation, not a claimed strategic improvement.

## Material limitations for evaluation

The source was designed around elimination/survival. In particular, its comments justify folding deep-stack AK/JJ/TT against large commitments because busting loses future hands. Imperial resets 100BB stacks every hand and rewards chip winnings; that rationale does not transfer. The conservative decisions are deliberately retained so B supplies an identifiable public strategy, and C can later evaluate any policy changes separately.

Twenty-four samples can produce noisy postflop equity, especially multiway and near a decision threshold. This port is not numerically equivalent to the source's much larger postflop estimates. It still evaluates random opponent holdings rather than action-conditioned ranges. Original draw approximations and seat-distance late-position rules are also retained. Source author performance statements, if recorded in the shortlist, are not evidence of this adapted bot's performance under Imperial rules.

Initial verification used Python **3.14.6**. Subsequent combined verification passed all 48 tests on actual Python **3.12.10**; see `runs/unit-tests-python312-final.txt`. The candidate uses only `random` and `time`. Final-byte 1,000-hand subprocess runs recorded one Floorfix timeout at eight seats and none at seven seats, with zero errors, invalid actions or bank exhaustion. See `runs/python312-8-1501-final.json` and `runs/python312-7-1502-final.json`. In-process timing excludes process communication and scheduler delays. Organizer-platform validation and competitive evaluation remain pending; retain the timing failure rather than inferring submission readiness.

## Verification performed

Run from the repository root; set `POKERBOTS_KIT` to the extracted official kit.

```powershell
python research/build_floorfix.py
python research/checks/test_floorfix.py
```

Build result: 34,881-byte standalone file and 169 equity classes. Test result: **11 tests passed in 0.247 seconds**.

- 12,000 random distinct 5-, 6- and 7-card hands: exact category/kicker equality and pairwise ordering against the unchanged official `engine/cards.py` oracle.
- All nine hand categories, wheel ordering, equivalent-hand ties, double-trips full houses and a board-playing river tie.
- All 13 pocket-pair table entries present; AA opens early position for 60 chips, 72 offsuit folds, and the inherited deep AK-versus-shove fold is retained.
- Legal raise bounds, short all-in ranges, forbidden raises and 2,000 randomized raise clamps.
- All 64 eight-seat seat/button combinations; zero-stack all-in opponents still counted.
- Current-history aggregation without persistent mutation, duplicate/stale summary rejection, next-hand counts, seat-zero aggressor identification and table reset.
- RNG isolation across agents and a deadline check before each Monte Carlo sample.
- Standalone size under 200KB and runtime import whitelist exactly `random`, `time`.

The same local run measured 200 in-process eight-seat flop decisions: median **0.446ms**, p95 **0.564ms**, p99 **0.627ms**, maximum **0.853ms**. This small synthetic timing probe is not a performance ranking or an IPC/time-bank compliance guarantee.

The official kit was used read-only from `../kit-review-helpers/official-kit/imperial-ai-hack-pokerbots-kit`. No arena, release bot, shared root file or remote repository was changed by this adaptation task.
