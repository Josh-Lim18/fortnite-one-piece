# Training the equity network on a CUDA PC

About an hour. Needs only the repo, [uv](https://docs.astral.sh/uv/) and an NVIDIA driver; uv fetches Python 3.12 and PyTorch. Run every command from the repo root. Labelling is CPU work on every core; only training uses the GPU.

## 1. Label about two million positions (30–40 min)

```
uv run --python 3.12 python equity_net/gen_data.py --positions 2000000 --samples 1000 --seed 101 --out equity_net/data
```

It prints positions done and seconds. One core labels about 70 positions a second, so 16 cores do two million in about 30 minutes. Check the rate after a minute. If it will run past 40 minutes, stop it with Ctrl-C: finished shards (500 positions each) are kept, and training reads whatever is in the folder. To add more later, run again with a new `--seed`. Reusing a seed rewrites the same positions.

## 2. Label the reference set (about 3 min)

```
uv run --python 3.12 python equity_net/gen_data.py --positions 560 --samples 20000 --seed 9001 --out equity_net/data/ref
```

These are 20,000-rollout labels. Training never reads this subfolder.

## 3. Train (about 5 min on a GPU)

Linux:

```
uv run --python 3.12 --with torch python equity_net/train.py --data equity_net/data --out equity_net/weights.txt --batch 4096 --epochs 30
```

Windows: PyPI's torch is CPU-only there, so add the CUDA index:

```
uv run --python 3.12 --with torch --index https://download.pytorch.org/whl/cu126 python equity_net/train.py --data equity_net/data --out equity_net/weights.txt --batch 4096 --epochs 30
```

The first line it prints must say `cuda`. It trains each shape in `SHAPES`, prints the held-out error of each, and keeps the most accurate. Keep the shapes as they are: they are sized by the bot's time budget per decision, not by the amount of data.

## 4. Check it beats the laptop weights

```
uv run --python 3.12 python equity_net/measure.py --ref equity_net/data/ref --weights equity_net/weights.txt
```

The `network` MAE must be below the laptop's figure: 0.0264 on this reference set (seed 9001), from 188,000 positions. If it isn't, discard the new weights.

## 5. Put it in the bot and test

```
uv run --python 3.12 python equity_net/paste.py
uv run --python 3.12 --with torch python equity_net/test_net.py
uv run --python 3.12 python tools/test_bot.py
```

Then commit `equity_net/weights.txt` and `bot.py` on a branch and hand the branch to Owen. The new weights replace the laptop ones only after `python3 tools/sim.py bot.py --vs <the bot.py with laptop weights> --rounds 24` shows they are no worse.
