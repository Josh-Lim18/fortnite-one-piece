"""Train the equity network on gen_data.py shards, keep the most accurate shape, export int8 weights for bot.py.

    uv run --with torch python equity_net/train.py --data equity_net/data --out equity_net/weights.txt

Soft-label cross-entropy on win/tie/lose, 5% held out, CUDA when available. Prints held-out mean absolute
equity error (equity = win + tie / 2) for each shape, float and int8, and writes the int8 one as one base85 line.
"""
import argparse
import base64
import glob
import json
import multiprocessing
import os
import struct
import sys
import time
from array import array

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import N_FEATURES, net_features  # noqa: E402
from infer import net_forward, net_load  # noqa: E402

# Hidden layers; each is 0.1-0.16 ms of quiet laptop time per query with the encoder (the tournament machine is
# 10-15x slower); (128, 32) measured 0.23 ms, over budget.
SHAPES = ((64, 32), (128,), (96, 32))


def _load(path):
    xs, ys = array("f"), array("f")
    with open(path) as f:
        for line in f:
            hero, board, widths, y = json.loads(line)
            xs.extend(net_features(hero, board, widths))
            ys.extend(y)
    return xs.tobytes(), ys.tobytes()


def load(folder):
    paths = sorted(glob.glob(os.path.join(folder, "*.jsonl")))
    if not paths:
        sys.exit("no *.jsonl shards in %s" % folder)
    fork = "fork" in multiprocessing.get_all_start_methods()  # spawn re-imports torch in every worker
    with multiprocessing.get_context("fork" if fork else "spawn").Pool() as pool:
        parts = pool.map(_load, paths)
    x = torch.frombuffer(bytearray(b"".join(p[0] for p in parts)), dtype=torch.float32).view(-1, N_FEATURES)
    y = torch.frombuffer(bytearray(b"".join(p[1] for p in parts)), dtype=torch.float32).view(-1, 3)
    return x, y


def mlp(shape):
    dims = (N_FEATURES,) + tuple(shape) + (3,)
    mods = []
    for a, b in zip(dims, dims[1:]):
        mods += [torch.nn.Linear(a, b), torch.nn.ReLU()]
    return torch.nn.Sequential(*mods[:-1])


def equity(p):
    return p[:, 0] + 0.5 * p[:, 1]


def mae(model, x, y, batch=65536):
    with torch.no_grad():
        err = sum((equity(torch.softmax(model(x[i:i + batch]), 1)) - equity(y[i:i + batch])).abs().sum().item()
                  for i in range(0, len(x), batch))
    return err / len(x)


def fit(shape, x, y, epochs, batch, lr, device):
    torch.manual_seed(0)
    model = mlp(shape).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    per = len(x) // batch
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr, total_steps=epochs * per)
    for _ in range(epochs):
        perm = torch.randperm(len(x), device=device)
        for i in range(per):
            idx = perm[i * batch:(i + 1) * batch]
            loss = -(y[idx] * torch.log_softmax(model(x[idx]), 1)).sum(1).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
    return model


def quantise(model):
    """A copy of the model whose weights are int8 per row times a float32 scale, and those (q, scale, bias)."""
    q_model = mlp([m.out_features for m in model if isinstance(m, torch.nn.Linear)][:-1])
    parts = []
    with torch.no_grad():
        for src, dst in zip((m for m in model if isinstance(m, torch.nn.Linear)),
                            (m for m in q_model if isinstance(m, torch.nn.Linear))):
            w = src.weight.detach().double().cpu()
            s = w.abs().max(1).values.clamp(min=1e-12) / 127.0
            q = (w / s[:, None]).round().clamp(-127, 127)
            s, b = s.float(), src.bias.detach().float().cpu()
            dst.weight.copy_(q.float() * s[:, None])
            dst.bias.copy_(b)
            parts.append((q.to(torch.int8), s, b))
    return q_model, parts


def export(parts):
    sizes = [parts[0][0].shape[1]] + [q.shape[0] for q, _, _ in parts]
    data = struct.pack("<B%dH" % len(sizes), len(parts), *sizes)
    for q, s, b in parts:
        data += struct.pack("<%db" % q.numel(), *q.flatten().tolist())
        data += struct.pack("<%df" % len(s), *s.tolist()) + struct.pack("<%df" % len(b), *b.tolist())
    return base64.b85encode(data).decode()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--batch", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=3e-3)
    a = ap.parse_args()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    t0 = time.time()
    x, y = load(a.data)
    g = torch.Generator().manual_seed(0)
    perm = torch.randperm(len(x), generator=g)
    k = len(x) // 20
    xva, yva, xtr, ytr = x[perm[:k]], y[perm[:k]], x[perm[k:]].to(device), y[perm[k:]].to(device)
    print("%d positions (%d held out), %s, loaded in %.0f s" % (len(x), k, device, time.time() - t0))
    best = None
    for shape in SHAPES:
        t1 = time.time()
        model = fit(shape, xtr, ytr, a.epochs, a.batch, a.lr, device).cpu()
        q_model, parts = quantise(model)
        err, q_err = mae(model, xva, yva), mae(q_model, xva, yva)
        text = export(parts)
        print("shape %-14s held-out MAE %.4f float, %.4f int8, %d bytes, %.0f s"
              % ("x".join(map(str, shape)), err, q_err, len(text), time.time() - t1))
        if best is None or q_err < best[0]:
            best = (q_err, shape, q_model, text)
    q_err, shape, q_model, text = best
    with torch.no_grad():  # the exported text must reproduce the PyTorch outputs it came from
        ref = torch.softmax(q_model(xva[:200]), 1)
    layers = net_load(text)
    drift = max(abs(a - b) for i in range(len(ref)) for a, b in zip(net_forward(layers, xva[i].tolist()), ref[i].tolist()))
    if drift > 1e-4:
        sys.exit("exported weights drift %.2g from PyTorch" % drift)
    with open(a.out, "w") as f:
        f.write(text + "\n")
    print("kept %s: held-out MAE %.4f; wrote %s (%d bytes, round-trip drift %.1g)"
          % ("x".join(map(str, shape)), q_err, a.out, len(text), drift))


if __name__ == "__main__":
    main()
