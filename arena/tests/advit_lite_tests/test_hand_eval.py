import random
import time

import eval7

from advit_lite.hand_eval import evaluate

EVAL7_CARDS = [eval7.Card(r + s) for s in "cdhs" for r in "23456789TJQKA"]


def eval7_score(cards):
    return eval7.evaluate([EVAL7_CARDS[c] for c in cards])


def idx(text):
    """'As Kd' -> card ints in the advit layout."""
    return ["cdhs".index(c[1]) * 13 + "23456789TJQKA".index(c[0]) for c in text.split()]


def test_known_hands_match_eval7():
    for hand in ["As Ks Qs Js Ts 2d 3c", "9s 9h 9d 9c Ah 2d 3c", "9s 9h 9d 5c 5h 2d 3c",
                 "2s 7s 9s Js Ks Ad 3c", "5s 6h 7d 8c 9h Ad Kc", "Ah 2d 3c 4s 5h 9d Kc",
                 "9s 9h 9d Ac Kh 2d 3c", "9s 9h 5d 5c Ah 2d 3c", "9s 9h Ad Kc 7h 2d 3c",
                 "Ah Kd 9c 7s 5h 3d 2c", "9s 9h 9d 5c 5h 5d 3c", "9s 9h 5d 5c 3h 3d Ac"]:
        assert evaluate(idx(hand)) == eval7_score(idx(hand)), hand


def test_random_hands_match_eval7_exactly():
    rng = random.Random(1)
    for i in range(100_000):
        cards = rng.sample(range(52), (5, 6, 7)[i % 3])
        assert evaluate(cards) == eval7_score(cards), cards


def test_fast_enough():
    rng = random.Random(2)
    hands = [rng.sample(range(52), 7) for _ in range(5000)]
    start = time.perf_counter()
    for cards in hands:
        evaluate(cards)
    assert (time.perf_counter() - start) / len(hands) < 0.0001  # under 100 microseconds each
