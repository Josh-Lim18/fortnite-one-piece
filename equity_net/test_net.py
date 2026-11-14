"""uv run --python 3.12 --with torch python equity_net/test_net.py"""
import inspect
import os
import random
import sys

import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import bot  # noqa: E402
import features  # noqa: E402
import gen_data  # noqa: E402
import infer  # noqa: E402
import train  # noqa: E402

WEIGHTS = open(os.path.join(HERE, "weights.txt")).read().strip()


def test_suit_renaming_and_card_order_never_change_features():
    rng = random.Random(1)
    for _ in range(2000):
        hero, board, widths = gen_data.position(rng)
        perm = rng.sample(range(4), 4)
        moved = [[(c >> 2) * 4 + perm[c & 3] for c in cards] for cards in (hero, board)]
        for cards in moved:
            rng.shuffle(cards)
        assert features.net_features(hero, board, widths) == features.net_features(moved[0], moved[1], widths[::-1])


def test_exported_weights_reproduce_pytorch_within_one_percent():
    rng = random.Random(2)
    xs = [features.net_features(*gen_data.position(rng)) for _ in range(300)]
    for shape in train.SHAPES:
        torch.manual_seed(len(shape) + shape[0])
        model = train.mlp(shape)
        with torch.no_grad():
            for m in model:
                if isinstance(m, torch.nn.Linear):
                    m.weight.mul_(3.0)  # sharper outputs than the default init, so the check has teeth
            ref = torch.softmax(model(torch.tensor(xs)), 1).tolist()
        layers = infer.net_load(train.export(train.quantise(model)[1]))
        drift = max(abs(a - b) for x, r in zip(xs, ref) for a, b in zip(infer.net_forward(layers, x), r))
        assert drift < 0.01, (shape, drift)


def test_aces_against_one_random_hand_preflop():
    p = infer.net_forward(infer.net_load(WEIGHTS), features.net_features([bot.card("As"), bot.card("Ah")], [], [1.0]))
    assert 0.84 <= p[0] + 0.5 * p[1] <= 0.86, p


def test_bot_carries_the_same_encoder_inference_and_weights():
    for name, mod in (("net_features", features), ("net_load", infer), ("net_forward", infer)):
        assert inspect.getsource(getattr(bot, name)) == inspect.getsource(getattr(mod, name)), name
    assert bot.N_FEATURES == features.N_FEATURES
    assert bot.NET_WEIGHTS == WEIGHTS, "paste equity_net/weights.txt into bot.NET_WEIGHTS"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
