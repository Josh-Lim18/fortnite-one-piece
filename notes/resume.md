# Resume note

## RESUMED Sat 15:20

- 15:48: picker merged as tag `picker-1` (main). Three layers in bot.py (86 KB): profiler with k=9 personalities fitted from all dealt hands in sim, tempered (0.05; calibration 0.31→0.53 and 0.90→0.95 still miss), autopicker with value shove, bluff, multi-street plan, call shover, barreller. Passes check_submission (0 errors, worst 2.9 ms, ≤1 s a round). Against v2 on the same deals (24 rounds, bb/100): house −53 ± 38 (earlier run +11 ± 43), house+starter +19 ± 42, starter +7 ± 11, opponents −11 ± 8. Not better: upload stays v1. Ablation shows the exploits carry the value: base alone −253 vs house, −32 vs opponents. Gaps: preflop base unpriced, call-shover not tracked, multiway crude, untuned.
- Owen's team had NO bot live at 15:28. v1 exported to ~/Downloads/poker-v1/bot.py (passes check); Owen to upload (or Josh) by 18:20 at the latest to reach 12 counted rounds. Message for Josh drafted in chat. `poker/bot` on GitHub still holds v0.

- Picker relaunched on Opus at 15:25 from `notes/slice-picker.md` (now with the multi-street value plan, calibration and k 4–12 follow-ups), merging the paused branch `worktree-agent-addff0dd05eab9c99` first.
- Standings at 15:25 (counted round 5 of 54): 39 teams; leaders about +90 bb/100; most between −45 and +45. With 39 teams at 7–8 seats there are few or no empty seats, so few house bots: the real field is team bots, and gains measured against house bots overstate us. Our team's name on the standings is unknown (not "fortnite-one-piece").

## PAUSED Sat 14 Nov about 15:00 GMT: 5-hour usage limit (history)

- Picker agent paused and reported (15:05): only the calibration fix is done, on `worktree-agent-addff0dd05eab9c99` (commits 02b8543, 16956ec), not merged and not verified (`model/test_model.py` and `scripts/verify.sh` not run). Temper 0.05 was the smallest value tried, so try lower. Calibration on held-out rounds: 0.35 stated vs 0.43 actual, 0.51 vs 0.56, 0.71 vs 0.65, 0.88 vs 0.84, 0.99 vs 1.00; two buckets miss the 0.05 target. Seats over 0.95 at 25/100/300 hands: 6% / 25% / 48%. Held-out log-loss 0.5350 tempered vs 0.5311 untempered vs 0.5446 before. The size bucket now marks facing a call of 800+ chips. Shover still never recognised. Not started: everything else in `notes/slice-picker.md`. Resume by relaunching the picker on Opus from that branch.
- Running when paused (superseded by the line above): the layer 3 autopicker agent (`notes/slice-picker.md`), branch `worktree-agent-addff0dd05eab9c99`, worktree `.claude/worktrees/agent-addff0dd05eab9c99`. It was told to commit and report progress. Its report may not have reached anyone: on resume, read that branch's log and diff against `main` first.
- The picker must include the overconfidence fix with a calibration table (stated top-type confidence within about 0.05 of the actual hit rate on held-out simulated rounds; held-out log-loss no worse). Owen asked for it.
- Adaption data job launched 14:28 on Owen's account (dataset a8c739b1-2834-463e-afec-b1de538b8168), estimated ready about 16:55; Adaption emails Owen.
- First steps on resume:
  1. Check the picker branch; finish or relaunch it on Opus from its brief and the progress it committed.
  2. Merge it through `scripts/verify.sh` and `team/tests/check_submission.py`.
  3. Open the finished Adaption dataset and check sample completions still end with our bot's action; then show Owen the AutoScientist training cost before launching.
  4. If Owen has given the data token: fetch hands, refit layer 2 with 4–12 types (Owen agreed the number should come from held-out score).
- Uploads close for Saturday at 19:30 and reopen Sunday 09:00–12:00. The recommended upload is still `demo-1` (v1); v2 (`demo-2`) and later are candidates for lane D to judge.


Updated Sat 14 Nov 2026, 13:25 GMT. Workflow: `hackathon-build`. Read `SPEC.md` first.

## Owner decisions

- Team plan (Owen's Notion page "Imperial AI Hack talks", section "Poker Bot — Four-person parallel workflow", confirmed allocation): lane A Josh, arena and integration, owns `arena/`, the starter-kit snapshot, shared config and the release `bot.py`; lanes B and C Nguyên Anh, sourcing public bots then improving the winning candidate; lane D Owen and Colin, evaluation and quality, owning `evaluation/`, `tests/` and result analysis, split between them with distinct files. Nobody reviews their own changes; Josh integrates serially. Owen said "I am doing D" (Sat 13:45). As of 13:45 the team repo's main holds only the agent board, and AGENTS.md has no lanes yet.

- Every assumption about an opponent must be adaptive to the profile (SPEC.md, Strategy); unusual moves are gated per seat by measured responses (Sat 13:40).

- Every routine task (code, simulations, data) goes to an Opus agent (`model: "opus"`). Fable is for planning and orchestration only; Owen moved this orchestrator session to Opus 5.5 at 13:15 because Fable was using too much of his plan.
- Enter the Best Use of Adaption prize as well as the poker track.
- Team repo: https://github.com/Josh-Lim18/fortnite-one-piece (public; Josh-Lim18 is team lead and owns every folder; Owen is `owenbonc`, a collaborator with write access and no area yet; its AGENTS.md says to ask the owner on the board, issue #1, before editing their folders). Owen's teammate's bot is the organisers' starter, unchanged.
- `origin` is the team repo. Owen approved one push (Sat 13:30): `main` went to branch `poker/bot` at 38bf920. Its history is unrelated to the team repo's `main`, so a PR there needs Josh. Each further push or board post needs Owen's go-ahead. A push and making the repo public (needed for Devpost by Sun 12:00) both need Owen's go-ahead.

## State

- `main` holds a working bot, tagged `demo-0`. `scripts/verify.sh` printed READY on it.
- Owen was sent `bot.py` to upload; as of 13:05 his team was not on the standings. He has not yet given the data token for `kit/fetch_hands.py`. Keep the token in `.env`, never in git.
- Local results so far (few rounds, noisy): bot against house bots +330 to +630 bb/100; against seven starter bots +394; the organisers' starter bot makes +1,250 to +1,600 against house bots.

## In flight

| Slice | Brief | Model | Branch | State |
|---|---|---|---|---|
| Simulator and tuner | `notes/slice-sim.md` | Sonnet | merged | on main, verify READY |
| Strategy (`bot.py`) | `notes/slice-strategy.md` | Opus | merged, tag `demo-1` | sent to Owen to upload |
| Opponent pool and analyser | `notes/slice-opponents.md` | Fable | merged | on main |
| Preflop matchup table | `notes/slice-matchups.md` | Sonnet | merged | on main; strategy agent told |
| Adaption dataset | `notes/slice-adaption-data.md` | Opus | merged | on main; data in `adaption/data/` (gitignored), sent to Owen |
| Bet-size reads, robust profiling, random-vs-strategic, tight fix | `notes/slice-reads.md` | Opus | stopped 13:50 (Owen: bot work is lane C now) | unmerged worktree `worktree-agent-a3a24d9fe3e3ea477` |
| Lane D: evaluation and tests in the team repo | `notes/slice-lane-d.md` | Opus | `team/` clone, branch `eval/benchmark` | running since 13:50 |
| Cheap randomness | `notes/slice-randomness.md` | Opus | merged, tag `demo-2` | no measurable change: house +6 ± 19, house+starter +7 ± 20, starter −1 ± 7, opponents −7.6 ± 5.7, self-play −0.3 ± 3.3 (48 rounds); passes lane D check; upload recommendation stays `demo-1` until lane D judges |
| Layer 2 opponent model | `notes/slice-model.md` | Opus | merged | held-out log-loss 0.545 full vs 0.558 counts vs 0.903 prior; types recovered 92% by 100 hands (shover misread); profiler 7 µs a prediction |
| Layer 3 autopicker | `notes/slice-picker.md` | Opus | its own worktree | running since 14:50; skill contract is in the Notion operating brief |
| Adaptive pressure moves | `notes/slice-pressure.md` | Opus | parked | bot work is lane C's |
| Adaption platform research | prompt only, read-only | Opus | none | reported; facts below |

Merge rule: in the agent's worktree `git merge main`, run `scripts/verify.sh`, then `git merge --ff-only <branch>` on main. `git worktree list` shows the worktrees.

## Next steps

0. Owen's work is lane D (Sat 13:50): `team/` is a clone of the team repo on `eval/benchmark`. When the lane D agent reports, review the branch; pushing it and opening a PR need Owen's go-ahead. The board post drafted for Owen is not posted.

1. Merge each slice as it reports.
2. Bot slices run one at a time, all on Opus: strategy (running), then `notes/slice-reads.md`, then `notes/slice-pressure.md`. Upload each that beats its predecessor. The strategy agent owns `bot.py` (`notes/slice-strategy.md`). When it reports, read its three comparisons, merge, and send `bot.py` to Owen to upload.
3. Counted rounds run Sat 15:00–19:25; the Sat 19:20 upload plays Sunday's first rounds.
4. When the token arrives: `python3 kit/fetch_hands.py --token ...`, run `tools/analyze.py hands/ --emit opponents/`, tune with `tools/tune.py`.
5. Adaption: when the research and dataset agents report, convert the dataset to the platform's format and walk Owen through starting the fine-tune (he signs in and claims credits under My Pass on the event site).

## Adaption run

- Sat 14:28: data adaption launched on Owen's account (dataset id a8c739b1-2834-463e-afec-b1de538b8168): 10,821 rows, instruction dataset, no expansion, recipes deduplication and reasoning traces only, length Concise, blueprint rule that every completion ends with the original action unchanged. Cost 109 of 1,250 credits. Estimated 146 min; Adaption emails Owen when ready.
- Next: when it finishes, open sample rows and check each completion still ends with our bot's action; then start Train with AutoScientist (under-10B model), showing Owen its credit cost before launch.

## Adaption facts (docs.adaptionlabs.ai, read Sat 13:10)

- Our `prompt`/`completion` JSONL uploads as-is: web app, API or Python SDK (`pip install adaption`), `processing_mode="raw"` with a `column_mapping` for the two columns. The `create` call's `data_format` defaults to `chat` for raw data: check it.
- Minimum rows: 1,000 for SFT; 10,000 for Gemma 26B+, Qwen 35B+ and NVIDIA models; 12,000 for DPO.
- AutoScientist loops: optional augmentation, train, evaluate against `target_win_rate`, adjust; `max_iterations` 1–5 (default 3). The app offers "Tiny AutoScientist" for models under 10B.
- Runtime is "hours"; credit cost is shown only in the app's order summary.
- Win rate is automatic: adapted model against base on evaluations derived from our dataset; a third-party card says an LLM judge on held-out prompts. No eval set needed from us.
- Output is a downloadable LoRA adapter or a push to Hugging Face; no hosted endpoint is documented.
- Not found: the leaderboard page, cost per run, Imperial-specific credit instructions. Owen should ask the sponsor.

## Agent log

| Agent | Model | Tokens | Result |
|---|---|---|---|
| Simulator and tuner | Sonnet | 89k | reported in 5 min; `sim.py bot.py --rounds 16` gave +539 ± 43 bb/100 against house bots in 19 s; noted the pool may not be running in parallel |
| Adaption research | Opus | 96k | reported in 4 min; facts above |
| Opponent pool | Fable | 189k | 18 min; READY; local: bot +343, starter +711 over 2 rounds (noisy); clone postflop rough; real hand-file shape unverified |
| Matchup table | Sonnet | 90k | 19 min; 20 KB table; AA range floor test moved to width 0.05 |
| Adaption dataset | Opus | 119k | 12 min; 10,821 train + 1,179 eval rows, 18.7 MB; terse completions (action only) |
| Strategy | Opus | 146k | 17 min; vs v0: +176 house, +128 house+starter, +40 starter, +27 ± 13 competent mix, −17 ± 7 tight-only (orchestrator's runs for the last two) |
