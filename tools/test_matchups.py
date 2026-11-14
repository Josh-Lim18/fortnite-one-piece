"""Sanity checks on the generated preflop matchup table."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
import bot  # noqa: E402
from matchups import MATCHUPS, decode, range_equity  # noqa: E402

t0 = time.perf_counter()
table = decode(MATCHUPS)
assert time.perf_counter() - t0 < 0.05, "decode too slow"

names = bot.ORDER.split()
ix = names.index
weights = [6 if n[0] == n[1] else 4 if n[2] == "s" else 12 for n in names]
assert len(table) == 169 and sum(weights) == 1326


def between(x, lo, hi):
    assert lo <= x <= hi, (x, lo, hi)


between(table[ix("AA")][ix("KK")], 0.80, 0.84)
between(table[ix("AKs")][ix("QQ")], 0.44, 0.48)
between(table[ix("72o")][ix("AA")], 0.10, 0.14)
for i in range(169):
    for j in range(169):
        assert abs(table[i][j] + table[j][i] - 1) < 0.005
for w in (0.03, 0.1, 0.25, 0.55, 1.0):
    assert range_equity(table, weights, ix("AA"), w) > 0.8
assert range_equity(table, weights, ix("72o"), 0.05) < 0.25
print("matchups ok")
