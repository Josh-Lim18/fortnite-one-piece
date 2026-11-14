"""The equity network and the bot's own Monte Carlo against a large Monte Carlo, and their time per query.

    python3 equity_net/gen_data.py --positions 560 --samples 20000 --seed 9001 --out equity_net/data/ref
    uv run --python 3.12 python equity_net/measure.py --ref equity_net/data/ref --weights equity_net/weights.txt

Postflop positions only, as the bot uses it. The Monte Carlo is bot.Agent._equity at its shipped settings,
timed back to back with the network on each position, so laptop load affects both alike.
"""
import argparse
import glob
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import bot  # noqa: E402
from features import net_features  # noqa: E402
from infer import net_forward, net_load  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--weights", required=True)
    a = ap.parse_args()
    net = net_load(open(a.weights).read().strip())
    rows = [json.loads(line) for p in sorted(glob.glob(os.path.join(a.ref, "*.jsonl"))) for line in open(p)]
    rows = [r for r in rows if r[1]]
    agent, clock = bot.Agent({"equity_net": False}), time.perf_counter
    err = {"net": [], "mc": []}
    spent = {"net": 0.0, "mc": 0.0}
    by_street = {}
    for hero, board, widths, (w, t, _) in rows:
        truth = w + 0.5 * t
        t0 = clock()
        p = net_forward(net, net_features(hero, board, widths))
        t1 = clock()
        mc = agent._equity(hero, board, widths, t1)
        t2 = clock()
        spent["net"] += t1 - t0
        spent["mc"] += t2 - t1
        err["net"].append(p[0] + 0.5 * p[1] - truth)
        err["mc"].append(mc - truth)
        by_street.setdefault(len(board), []).append(abs(err["net"][-1]))
    n = len(rows)
    print("%d postflop positions against %s" % (n, a.ref))
    for k, name in (("net", "network"), ("mc", "Monte Carlo, shipped")):
        e = err[k]
        mae = sum(map(abs, e)) / n
        se = (sum((abs(x) - mae) ** 2 for x in e) / (n - 1) / n) ** 0.5
        print("%-22s MAE %.4f ± %.4f, mean signed error %+.4f, %.0f us per query"
              % (name, mae, se, sum(e) / n, spent[k] / n * 1e6))
    print("network MAE by board size: " + ", ".join("%d cards %.4f" % (b, sum(v) / len(v)) for b, v in sorted(by_street.items())))
    print("network time / Monte Carlo time: %.2f" % (spent["net"] / spent["mc"]))


if __name__ == "__main__":
    main()
