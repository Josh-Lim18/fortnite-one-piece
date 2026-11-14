"""bot.score must order hands exactly as the tournament engine's evaluator does."""
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "kit"))
sys.path.insert(0, ROOT)  # last, so `bot` is ours and not the kit's starter
from engine.cards import evaluate  # noqa: E402
import bot  # noqa: E402

rng = random.Random(7)
for _ in range(200000):
    deal = rng.sample(range(52), 9)
    board, a, b = deal[:5], deal[5:7], deal[7:]
    ours = (bot.score(a + board) > bot.score(b + board)) - (bot.score(a + board) < bot.score(b + board))
    theirs = (evaluate(a + board) > evaluate(b + board)) - (evaluate(a + board) < evaluate(b + board))
    assert ours == theirs, (a, b, board)
assert abs(bot.PCT[12 * 26 + 12 * 2] - 6 / 1326) < 1e-9 and max(bot.PCT) == 1.0
print("score matches engine on 200000 deals")
