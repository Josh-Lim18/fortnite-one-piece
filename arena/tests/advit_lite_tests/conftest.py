"""Real game states recorded from arena games, in Fullhouse and kit formats, plus the original bot."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from arena.agent_bot import to_kit_state
from arena.baselines import RandomBot
from arena.engine import TableConfig
from arena.match import run_match

ARENA = Path(__file__).resolve().parents[2]
ADVIT = ARENA / "bots" / "advitrocks9"


def _load_fullhouse_host():
    spec = importlib.util.spec_from_file_location("fullhouse_host", ARENA / "bots" / "hosts" / "fullhouse_host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Recorder(RandomBot):
    """Plays randomly; records each observation it is shown."""

    def __init__(self, seed, sink):
        super().__init__(seed)
        self.sink = sink

    def act(self, obs):
        self.sink.append(obs)
        return super().act(obs)


@pytest.fixture(scope="session")
def arena_observations():
    """About 5,000 decisions from 2-, 3-, 6- and 8-player tables at 2,000 chips, 10/20 blinds."""
    observations = []
    for n, seed in ((2, 1), (3, 2), (6, 3), (8, 4)):
        bots = [_Recorder(seed * 10 + i, observations) for i in range(n)]
        for i, bot in enumerate(bots):
            bot.name = f"r{i}"
        run_match(bots, deals=30, seed=seed, config=TableConfig(10, 20, 2000))
    return observations


@pytest.fixture(scope="session")
def fullhouse_states(arena_observations):
    host = _load_fullhouse_host()
    return [host.to_state(obs, []) for obs in arena_observations]


@pytest.fixture(scope="session")
def kit_states(arena_observations):
    return [to_kit_state(obs) for obs in arena_observations]


@pytest.fixture(scope="session")
def preflop_tables():
    data = np.load(ADVIT / "data" / "preflop_equity.npz")
    return ([float(x) for x in data["paired"]],
            [[float(x) for x in row] for row in data["suited"]],
            [[float(x) for x in row] for row in data["offsuit"]])


@pytest.fixture(scope="session")
def advit_dir():
    """The original bot: puts bots/advitrocks9 on sys.path so `import bot.features` works."""
    if str(ADVIT) not in sys.path:
        sys.path.insert(0, str(ADVIT))
    return ADVIT
