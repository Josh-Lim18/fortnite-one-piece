# Resume note

Updated Sat 14 Nov 2026, about 13:35 GMT. Workflow: `hackathon-build`. Read `SPEC.md` first.

## Owner decisions

- Every routine task (code, merges beyond one command, simulations, data) goes to an Opus agent (`model: "opus"`). Fable is for planning and orchestration only, and its turns are kept few: it was using too much of Owen's plan (Sat 13:10).
- Enter the Best Use of Adaption prize as well as the poker track.
- Nothing is pushed and no remote exists. A push and making the repo public (needed for Devpost by Sun 12:00) both need Owen's go-ahead.

## State

- `main` holds a working bot, tagged `demo-0`. `scripts/verify.sh` printed READY on it.
- Owen was sent `bot.py` to upload; as of 13:05 his team was not on the standings. He has not yet given the data token for `kit/fetch_hands.py`. Keep the token in `.env`, never in git.
- Local results so far (few rounds, noisy): bot against house bots +330 to +630 bb/100; against seven starter bots +394; the organisers' starter bot makes +1,250 to +1,600 against house bots.

## In flight

| Slice | Brief | Model | Branch | State |
|---|---|---|---|---|
| Simulator and tuner | `notes/slice-sim.md` | Sonnet | merged | on main, verify READY |
| Strategy (`bot.py`) | `notes/slice-strategy.md` | Opus | its own worktree | running |
| Opponent pool and analyser | `notes/slice-opponents.md` | Fable (launched before the Opus rule) | its own worktree | running |
| Preflop matchup table | `notes/slice-matchups.md` | Sonnet | its own worktree | running |
| Adaption dataset | `notes/slice-adaption-data.md` | Opus | its own worktree | running |
| Adaption platform research | prompt only, read-only | Opus | none | reported; facts below |

Merge rule: in the agent's worktree `git merge main`, run `scripts/verify.sh`, then `git merge --ff-only <branch>` on main. `git worktree list` shows the worktrees.

## Next steps

1. Merge each slice as it reports.
2. The strategy agent owns `bot.py` (`notes/slice-strategy.md`). When it reports, read its three comparisons, merge, and send `bot.py` to Owen to upload.
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
