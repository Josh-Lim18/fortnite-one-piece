# Resume note

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
| Bet-size reads, robust profiling, random-vs-strategic, tight fix | `notes/slice-reads.md` | Opus | its own worktree | running since 13:32 |
| Adaptive pressure moves | `notes/slice-pressure.md` | Opus | not started | launch after reads merges (same file) |
| Adaption platform research | prompt only, read-only | Opus | none | reported; facts below |

Merge rule: in the agent's worktree `git merge main`, run `scripts/verify.sh`, then `git merge --ff-only <branch>` on main. `git worktree list` shows the worktrees.

## Next steps

1. Merge each slice as it reports.
2. Bot slices run one at a time, all on Opus: strategy (running), then `notes/slice-reads.md`, then `notes/slice-pressure.md`. Upload each that beats its predecessor. The strategy agent owns `bot.py` (`notes/slice-strategy.md`). When it reports, read its three comparisons, merge, and send `bot.py` to Owen to upload.
3. Counted rounds run Sat 15:00–19:25; the Sat 19:20 upload plays Sunday's first rounds.
4. When the token arrives: `python3 kit/fetch_hands.py --token ...`, run `tools/analyze.py hands/ --emit opponents/`, tune with `tools/tune.py`.
5. Adaption: when the research and dataset agents report, convert the dataset to the platform's format and walk Owen through starting the fine-tune (he signs in and claims credits under My Pass on the event site).

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
