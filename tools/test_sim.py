"""python3 tools/test_sim.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim  # noqa: E402

EX = os.path.join(sim.ROOT, "kit", "examples")
POOL = [sim.load(os.path.join(EX, f)) for f in sorted(os.listdir(EX)) if f.endswith(".py")]


def table():
    return [POOL[i % len(POOL)] for i in range(sim.SEATS)]


def test_zero_sum():
    assert sum(sim.run(table(), 60, 3)) == 0


def test_repeatable():
    assert sim.run(table(), 60, 5) == sim.run(table(), 60, 5)


def test_self_compare_is_zero():
    m, se = sim.compare(POOL[0], POOL[0], POOL, 4, 7, hands=40)
    assert m == 0 and se == 0, (m, se)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
