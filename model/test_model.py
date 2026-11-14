"""The fitted model must beat prior-only on fresh rounds, read calling stations as non-folders within 30 hands,
give valid probabilities, and stay small enough to paste into bot.py.

    python3 model/test_model.py
"""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from dataset import load, record, simulate, summaries  # noqa: E402
from evaluate import score  # noqa: E402
from fitted import FITTED  # noqa: E402
from profiler import CELLS, Profiler, STREETS, cell  # noqa: E402

STATION = "kit/examples/calling_station.py"


def facing_bet_fold(table):
    """A type's fold rate facing a bet, weighted by how often each bet-facing situation comes up."""
    cells = [c for c in range(CELLS) if (c // 3) % 5]
    w = sum(FITTED["share"][c] for c in cells)
    return sum(FITTED["share"][c] * table[c][0] for c in cells) / w


def main():
    size = os.path.getsize(os.path.join(HERE, "fitted.py"))
    assert size < 30_000, "fitted.py is %d bytes" % size

    with tempfile.TemporaryDirectory() as tmp:
        files = simulate(8, 99, tmp)  # rounds the model never saw
        r = score(FITTED, files)
        print("fresh rounds: log-loss full %.4f, counts %.4f, prior %.4f" % (r["full"], r["counts"], r["prior"]))
        assert r["full"] < r["counts"] < r["prior"], r
        assert r["us_observe"] < 200 and r["us_predict"] < 200, r

        bots = [STATION, "opponents/nit.py", STATION, "opponents/maniac.py", "kit/examples/tight_aggressive.py",
                STATION, "opponents/equity_tag.py"]
        rnd, _ = load(record(bots, 7, os.path.join(tmp, "stations.json"), hands=30))
        prof = Profiler(len(bots), FITTED)
        t0 = time.perf_counter()
        for s in summaries(rnd):
            prof.observe_hand(s)
        print("observe_hand: %.2f ms per hand" % ((time.perf_counter() - t0) * 1000 / 30))
        for seat, bot in enumerate(bots):
            w = prof.type_posterior(seat)
            top = w.index(max(w))
            fold = facing_bet_fold(FITTED["types"][top])
            if bot == STATION:
                print("calling station seat %d after 30 hands: type %d (posterior %.3f), folds to bets %.1f%%"
                      % (seat, top, max(w), 100 * fold))
                assert fold < 0.03, (seat, top, fold)
            assert abs(sum(w) - 1) < 1e-9 and min(w) >= 0
            for c in range(CELLS):
                p = prof.predict(seat, c)
                assert len(p) == 3 and min(p) >= 0 and abs(sum(p) - 1) < 1e-9, (seat, c, p)
            for street in range(len(STREETS)):
                for action in (1, 2):
                    d = prof.range(seat, street, action)
                    assert len(d) == 10 and min(d) >= 0 and abs(sum(d) - 1) < 1e-6, (seat, street, action, d)
        assert prof.predict(0, cell(1, 2, 1))[0] < 0.05  # a station facing a flop bet
    print("ok")


if __name__ == "__main__":
    main()
