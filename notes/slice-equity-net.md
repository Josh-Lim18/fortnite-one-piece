# Slice: equity network for the base layer

**Files you own:** `equity_net/` (new), `bot.py` (integration only, behind a param), `tools/test_bot.py`, `tools/baseline_bot.py`. **Time box:** 120 minutes.

The base layer estimates postflop equity (our chance of winning at showdown against each opponent's likely hands) with about 60 Monte Carlo rollouts, capped at 1.5 ms. That is roughly ±6% noise, and every layer above it prices its choices on that number. Replace it with a small neural network trained offline on exact labels, and evaluated in pure Python inside `bot.py`.

## Constraints (measured, Sat 15:12, Python 3.12, standard library only)

| Network | Parameters | Forward pass | Size as int8 text |
|---|---|---|---|
| 60→128→128→64→3 | 33k | 1.0 ms | 41 KB |
| 60→192→192→96→3 | 68k | 1.9 ms | 85 KB |

`bot.py` is about 86 KB now, against a 200 KB limit. Budget: at most about 60 KB for the network, and at most about 1 ms per query. The picker may query several bet sizes per decision; read `notes/slice-picker.md` and `Agent._pick` for how equity is used. Inference must be pure Python: `sum(map(operator.mul, row, x))` per row, as in the timing above.

## Build

1. **`equity_net/features.py`:** pure standard library. It is the single feature encoder used in training and in `bot.py`. Inputs:
   - our two cards and the board, encoded compactly (rank and suit structure, not 52-wide one-hot unless it fits the budget);
   - the street;
   - the number of opponents (1–3; more is treated as 3);
   - each opponent's range width (the top share of hands it plays, as `bot.py` uses it: see `_equity` and `hand_pct`).

   Outputs: win, tie, lose.
2. **`equity_net/gen_data.py`:** labels positions with `bot.score` by Monte Carlo against opponents drawn from their range widths, the same model as `bot.Agent._equity`, with enough samples per position that label noise is small (about 1,000+). Use `multiprocessing`. It must run on any machine with Python 3.12: the laptop (small sample) and Isaac's PC (millions of positions). Write shards to `equity_net/data/` (gitignored).
3. **`equity_net/train.py`:** PyTorch, run with `uv run --with torch python equity_net/train.py --data equity_net/data --out equity_net/weights.txt`. It:
   - uses CUDA when available, CPU otherwise;
   - trains with soft-label cross-entropy on win/tie/lose;
   - holds out 5%;
   - tries 2–3 shapes inside the budget and keeps the most accurate;
   - quantises to int8 per row with a float scale;
   - writes a b85 text block plus scales.

   It prints held-out mean absolute equity error.
4. **`equity_net/infer.py`:** pure standard library. It decodes the weights and runs the forward pass, to be pasted into `bot.py` beside the encoder.
5. **Integration:**
   - In `bot.py`, `_equity` uses the network when `PARAMS["equity_net"]` is true and the weights are present. Otherwise it keeps the Monte Carlo.
   - Ship it switched off until the measurement below shows it helps.

## Laptop run (proof, now)

Generate a small dataset on the laptop (about 200k positions; keep each command under about 5 minutes, using `multiprocessing`), train on CPU, and report:
- held-out mean absolute equity error against labels;
- error against a very large Monte Carlo (20,000 rollouts) on 500 fresh positions, compared with the current 60-rollout estimate on the same positions;
- forward-pass time under `uv run --python 3.12`;
- the size added to `bot.py`.

Then integrate the laptop-trained weights and report `tools/sim.py bot.py --vs tools/baseline_bot.py --rounds 24` with the net on, against `kit/examples/*.py`, `kit/bot.py` and `opponents/*.py`, plus lane D's check: `python3 team/tests/check_submission.py bot.py --kit kit`.

## Isaac's PC (later, by a person)

Write `equity_net/RUN_ON_GPU.md`: the exact commands to generate millions of positions and train on a CUDA machine. It needs only Python 3.12, uv and the repo, and should take about an hour. Do not SSH anywhere yourself.

## Test

`equity_net/test_net.py`:
- the encoder gives identical features for suit-permuted equivalent hands;
- the exported weights round-trip through `infer.py` to within 1% of the PyTorch outputs;
- AA against one random hand preflop reads 0.84–0.86 equity.
