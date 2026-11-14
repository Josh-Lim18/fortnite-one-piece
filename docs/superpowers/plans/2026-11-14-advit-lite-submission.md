# advit_lite: advitrocks9 converted to the hackathon rules — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn advitrocks9 (Fullhouse 2026 Deep CFR bot, numpy + eval7, 577 KB model) into one standard-library-only `bot.py` for the AlgoSoc platform: under 200 KB, under 10 ms per decision, playing the same strategy.

**Architecture:** A package `arena/src/advit_lite/` ports the original pieces to plain Python one module at a time: an eval7-compatible hand evaluator, the 51-feature encoder, the network with 8-bit weights, the decision policy, and an adapter between the AlgoSoc kit's `state` and the Fullhouse format the network was trained on. A build script quantizes the weights and concatenates the package into a single `dist/advit_lite/bot.py`. Every module is tested against the original advitrocks9 on real game states recorded from the arena.

**Tech Stack:** Python 3.9+ standard library (the bot); numpy, eval7, PokerKit and pytest in the arena's dev environment (tests and build only); uv.

**Spec:** "Combined bot design brief", https://claude.ai/artifact/BXxoyt3PBM1RJWYscfSPTZ (section "Fitting 200 KB and 10 ms" and the advitrocks9 rows). This plan is build steps 1–3 of that brief. AlgoSoc kit API: `research_notes/Open source poker bot candidates/competition_proven_bots.md`, section 2.

## Global Constraints

- The submitted `bot.py` imports only the Python standard library and runs on Python 3.9+ (the kit says "No dependencies beyond Python 3.9+").
- The platform imports `Agent` from `bot.py`; `act(state)` returns `{"action": "fold"|"check"|"call"|"raise"|"all_in", "amount": int}`; raise amounts are "raise to"; a fresh `Agent()` is created for every table.
- Size: `bot.py` ≤ 200,000 bytes (the organisers' "200 KB", read conservatively).
- Time: ≤ 10 ms per decision on the platform; on a dev laptop the median must stay under 5 ms and the 99th percentile under 9 ms. Measured while planning: about 4 ms median, 7.0–7.4 ms at the 99th percentile, so the margin is thin; a slower platform CPU is the main risk (a late decision becomes a check or fold, not a crash).
- No file or network access at decision time; everything the bot needs is embedded in `bot.py`.
- Keep advitrocks9's MIT attribution (Copyright (c) 2026 Advit Arora): `arena/bots/advitrocks9/LICENSE` stays, and the bundle's first line credits it.
- All commands run from `arena/`. If `UV_PROJECT_ENVIRONMENT` is set on your machine, unset it first (`env -u UV_PROJECT_ENVIRONMENT uv run ...`), or uv installs into that other environment and removes its packages.
- Work on branch `feat/poker-arena` (it holds the vendored advitrocks9 under `arena/bots/advitrocks9/`).

## Background the engineer needs

- **advitrocks9's decision path** (`arena/bots/advitrocks9/bot/bot.py:353` `decide`): preflop with ≤ 12 big blinds effective → push/fold charts; otherwise encode the state into 51 features (`bot/features.py:624` `encode_state_dict`), run the network (`bot/deep_cfr_lookup.py`), regret-match its output into probabilities over 5 actions (fold, check/call, bet half pot, bet pot, all-in), sample one, and convert it to an engine action.
- **Units:** advitrocks9 assumes a 100-chip big blind and 10,000-chip stacks. The kit uses 2,000-chip stacks with blinds rising from 10/20. The adapter scales chips by `k = 100 / big_blind` on the way in and divides raise amounts by `k` on the way out.
- **eval7 score:** feature 1 is `eval7.evaluate(cards) / 135004160`, so our evaluator must return eval7's exact integers: hand type << 24, then up to five 4-bit rank slots at shifts 16, 12, 8, 4, 0 (verified on 300,000 hands while writing this plan).
- **Measured while writing this plan** (prototype of exactly the code below, 11,174 arena states; all 18 tests in this plan passed against it): features identical to the original (max difference 2.4e-7); full-precision port vs original probabilities worst shift 5e-6; 8-bit port: same top action 98.3%, mean shift 0.019; about 4 ms median per decision, 7.0–7.4 ms at the 99th percentile; bundle 169,379 bytes.
- **One deliberate change:** the original `_position()` indexes `POSITIONS_6MAX[offset]` and raises `IndexError` at offsets 6–7 (7–8-player tables), which makes `decide` fall back to check/call. The port maps those seats to `"CO"`.

## File Structure

| File | Responsibility |
|---|---|
| `arena/src/advit_lite/__init__.py` | Package marker |
| `arena/src/advit_lite/hand_eval.py` | eval7-compatible 5–7 card evaluator |
| `arena/src/advit_lite/features.py` | 51-feature encoder and legal-action mask (port of `bot/features.py`) |
| `arena/src/advit_lite/network.py` | Weight decoding (int8 blob) and the network forward pass + regret matching |
| `arena/src/advit_lite/policy.py` | `decide()`: push/fold, network, sampling, engine action (port of `bot/bot.py`) |
| `arena/src/advit_lite/kit_adapter.py` | AlgoSoc kit `state` ↔ Fullhouse `game_state`, chip scaling |
| `arena/src/advit_lite/agent.py` | `Agent` class, the platform entry point |
| `arena/src/advit_lite/weights_data.py` | Generated: int8 weight blob, metadata, preflop tables |
| `arena/tools/build_advit_lite.py` | Quantize, generate `weights_data.py`, bundle `dist/advit_lite/bot.py` |
| `arena/tests/advit_lite_tests/conftest.py` | Fixtures: recorded Fullhouse and kit states, the original bot |
| `arena/tests/advit_lite_tests/test_*.py` | One test file per module, plus the bundle |
| `arena/pyproject.toml` | Add `src/advit_lite` to the wheel packages |
| `arena/bots.toml` | Register `advit-lite` (agent type, 10 ms limit) |
| `arena/.gitignore` | Ignore `dist/` |

---

### Task 1: eval7-compatible hand evaluator

**Files:**
- Create: `arena/src/advit_lite/__init__.py`
- Create: `arena/src/advit_lite/hand_eval.py`
- Modify: `arena/pyproject.toml` (`[tool.hatch.build.targets.wheel]`)
- Test: `arena/tests/advit_lite_tests/test_hand_eval.py` (the folder gets no `__init__.py`: with one, pytest imports it as a package named after the folder; keep the `_tests` suffix so it can never shadow `advit_lite`)

**Interfaces:**
- Produces: `advit_lite.hand_eval.evaluate(cards: list[int]) -> int`. Cards are ints 0–51 = `suit * 13 + rank`, rank 0–12 for 2..A, suits in `"cdhs"` order. Returns exactly `eval7.evaluate()`'s value.

- [ ] **Step 1: Register the package and write the failing test**

In `arena/pyproject.toml`, change the wheel packages line to:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/arena", "src/advit_lite"]
```

Create `arena/src/advit_lite/__init__.py`:

```python
"""advitrocks9 converted to the AlgoSoc rules: standard library only, one file, under 200 KB and 10 ms."""
```

Create `arena/tests/advit_lite_tests/test_hand_eval.py` (no `__init__.py` in that folder):

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/advit_lite_tests/test_hand_eval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'advit_lite.hand_eval'`

- [ ] **Step 3: Write the evaluator**

Create `arena/src/advit_lite/hand_eval.py`:

```python
"""eval7-compatible 5-7 card hand evaluator, standard library only.

Cards are ints 0-51: suit * 13 + rank, rank 0-12 for 2..A, suits in "cdhs" order
(the layout advitrocks9's features use). evaluate() returns exactly what
eval7.evaluate() returns: hand type << 24, then up to five 4-bit rank slots
at shifts 16, 12, 8, 4, 0.
"""

_SHIFTS = (16, 12, 8, 4, 0)


def _pack(hand_type, ranks):
    value = hand_type << 24
    for rank, shift in zip(ranks, _SHIFTS):
        value |= rank << shift
    return value


def _straight_top(rank_set):
    """Highest rank topping a 5-card straight in rank_set, or -1. A plays low in the wheel."""
    for top in range(12, 3, -1):
        if all((top - i) in rank_set for i in range(5)):
            return top
    if {12, 0, 1, 2, 3} <= rank_set:
        return 3
    return -1


def evaluate(cards):
    counts = [0] * 13
    by_suit = ([], [], [], [])
    for card in cards:
        rank = card % 13
        counts[rank] += 1
        by_suit[card // 13].append(rank)

    for suited in by_suit:
        if len(suited) >= 5:
            top = _straight_top(set(suited))
            if top >= 0:
                return _pack(8, (top,))
            flush = sorted(suited, reverse=True)[:5]
            break
    else:
        flush = None

    quads = [r for r in range(12, -1, -1) if counts[r] == 4]
    trips = [r for r in range(12, -1, -1) if counts[r] == 3]
    pairs = [r for r in range(12, -1, -1) if counts[r] == 2]
    present = [r for r in range(12, -1, -1) if counts[r]]

    if quads:
        kicker = max(r for r in present if r != quads[0])
        return _pack(7, (quads[0], kicker))
    if trips and (len(trips) > 1 or pairs):
        pair = max(trips[1:] + pairs)
        return _pack(6, (trips[0], pair))
    if flush:
        return _pack(5, flush)
    top = _straight_top(set(present))
    if top >= 0:
        return _pack(4, (top,))
    if trips:
        kickers = [r for r in present if r != trips[0]][:2]
        return _pack(3, [trips[0]] + kickers)
    if len(pairs) >= 2:
        kicker = max(r for r in present if r not in pairs[:2])
        return _pack(2, (pairs[0], pairs[1], kicker))
    if pairs:
        kickers = [r for r in present if r != pairs[0]][:3]
        return _pack(1, [pairs[0]] + kickers)
    return _pack(0, present[:5])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv sync -q && uv run pytest tests/advit_lite_tests/test_hand_eval.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add arena/pyproject.toml arena/src/advit_lite/__init__.py arena/src/advit_lite/hand_eval.py arena/tests/advit_lite_tests/test_hand_eval.py
git commit -m "Add eval7-compatible standard-library hand evaluator for advit_lite"
```

---

### Task 2: Feature encoder port

**Files:**
- Create: `arena/src/advit_lite/features.py`
- Create: `arena/tests/advit_lite_tests/conftest.py`
- Test: `arena/tests/advit_lite_tests/test_features.py`

**Interfaces:**
- Consumes: `advit_lite.hand_eval.evaluate` (Task 1).
- Produces:
  - `advit_lite.features.encode_state(state: dict, preflop: tuple) -> tuple[list[float], list[bool]]` — 51 features and a 5-entry legal mask; `preflop = (paired: list[13], suited: list[13][13], offsuit: list[13][13])`.
  - `advit_lite.features.infer_dealer(state: dict, n_players: int | None = None) -> int`
  - `advit_lite.features.BIG_BLIND = 100`
  - Fixtures (conftest): `fullhouse_states` (list of Fullhouse game_state dicts), `kit_states` (list of kit state dicts), `preflop_tables` (the tuple above), `advit_dir` (Path to `bots/advitrocks9`).

- [ ] **Step 1: Write the fixtures and the failing test**

Create `arena/tests/advit_lite_tests/conftest.py`:

```python
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
```

Create `arena/tests/advit_lite_tests/test_features.py`:

```python
import numpy as np

from advit_lite.features import BIG_BLIND, encode_state, infer_dealer


def test_features_match_the_original_on_recorded_states(fullhouse_states, preflop_tables, advit_dir):
    from bot.features import encode_state_dict  # the original, numpy

    assert len(fullhouse_states) > 3000
    for state in fullhouse_states:
        f0, l0 = encode_state_dict(state)
        f1, l1 = encode_state(state, preflop_tables)
        assert len(f1) == 51
        assert np.allclose(np.asarray(f0, dtype=np.float64), f1, atol=1e-6), state
        assert [bool(x) for x in l0] == l1, state


def test_dealer_inferred_from_blinds():
    heads_up = {"players": [{}, {}], "action_log": [{"seat": 1, "action": "small_blind"}, {"seat": 0, "action": "big_blind"}]}
    six = {"players": [{}] * 6, "action_log": [{"seat": 3, "action": "small_blind"}, {"seat": 4, "action": "big_blind"}]}
    assert infer_dealer(heads_up) == 1
    assert infer_dealer(six) == 2
    assert BIG_BLIND == 100
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/advit_lite_tests/test_features.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'advit_lite.features'`

- [ ] **Step 3: Write the encoder**

Create `arena/src/advit_lite/features.py`:

```python
"""advitrocks9's 51-feature state encoding, ported from numpy to plain Python.

Input: a Fullhouse-format game_state dict (chips in Fullhouse units: 100-chip big blind).
Output: (features, legal) where features is a list of 51 floats and legal a list of 5 bools,
identical to bot/features.py:encode_state_dict in the original.
"""

from advit_lite.hand_eval import evaluate

FEATURE_DIM = 51
N_ACTIONS = 5
STARTING_STACK = 10_000
BIG_BLIND = 100
LEGAL_MASK_OFFSET = 46
MAX_EVAL7_SCORE = 135004160.0
_RANKS = "23456789TJQKA"
_SUITS = "cdhs"


def card_index(card):
    """'As' -> suit * 13 + rank, suits in 'cdhs' order (the original's layout)."""
    return _SUITS.index(card[1]) * 13 + _RANKS.index(card[0])


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def infer_dealer(state, n_players=None):
    if n_players is None:
        n_players = len(state.get("players", [])) or 2
    n_players = max(int(n_players), 2)
    if state.get("dealer") is not None:
        return int(state["dealer"]) % n_players
    small_blind = big_blind = None
    for entry in state.get("action_log") or []:
        action = entry.get("action")
        if action == "small_blind" and entry.get("seat") is not None:
            small_blind = int(entry["seat"])
        elif action == "big_blind" and entry.get("seat") is not None:
            big_blind = int(entry["seat"])
        if small_blind is not None and big_blind is not None:
            break
    if small_blind is not None:
        return small_blind % n_players if n_players == 2 else (small_blind - 1) % n_players
    if big_blind is not None:
        return (big_blind - 1) % n_players if n_players == 2 else (big_blind - 2) % n_players
    return 0


def _street_index(street_name):
    return {"preflop": 0, "flop": 1, "turn": 2, "river": 3}.get(street_name, 0)


def _street_action_segment(log):
    for i in range(len(log) - 1, -1, -1):
        if log[i].get("action") == "deal":
            return log[i + 1:]
    return log


def _replay_betting_rounds(log, players, current_street_name):
    target_street = _street_index(current_street_name)
    seats = {int(p.get("seat", idx)) for idx, p in enumerate(players)}
    if not seats:
        seats = {int(e["seat"]) for e in log if e.get("seat") is not None}
    st = {"street": 0, "current_bet": 0, "last_full_raise": BIG_BLIND, "street_bets": {}, "pending": set(seats)}
    invested = {}
    folded = set()
    all_in = set()
    current_segment = []
    current_n_raises = 0
    current_last_raiser = None

    def active_seats():
        return {seat for seat in seats if seat not in folded and seat not in all_in}

    def advance_street():
        st["street"] = min(st["street"] + 1, 3)
        st["current_bet"] = 0
        st["last_full_raise"] = BIG_BLIND
        st["street_bets"] = {}
        st["pending"] = active_seats()

    for entry in log:
        action = entry.get("action")
        if action == "deal":
            advance_street()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        seats.add(seat)
        amount = max(_safe_int(entry.get("amount", 0)), 0)
        if action not in ("small_blind", "big_blind") and not st["pending"] and st["street"] < target_street:
            advance_street()
        if st["street"] == target_street:
            current_segment.append(entry)
        bets = st["street_bets"]
        if action in ("small_blind", "big_blind"):
            inc = amount
            bets[seat] = bets.get(seat, 0) + inc
            st["current_bet"] = max(st["current_bet"], bets[seat])
        elif action == "fold":
            inc = 0
            folded.add(seat)
            st["pending"].discard(seat)
        elif action == "check":
            inc = 0
            st["pending"].discard(seat)
        elif action == "call":
            inc = amount
            bets[seat] = bets.get(seat, 0) + inc
            st["pending"].discard(seat)
        elif action in ("raise", "all_in"):
            prev_bet = st["current_bet"]
            prev_seat_bet = bets.get(seat, 0)
            inc = max(0, amount - prev_seat_bet)
            bets[seat] = max(prev_seat_bet, amount)
            st["current_bet"] = max(st["current_bet"], bets[seat])
            st["pending"].discard(seat)
            if action == "all_in":
                all_in.add(seat)
            raise_size = max(0, st["current_bet"] - prev_bet)
            if raise_size > 0 and raise_size >= st["last_full_raise"]:
                st["last_full_raise"] = raise_size
                st["pending"] = {s for s in active_seats() if s != seat}
                if st["street"] == target_street:
                    current_n_raises += 1
                    current_last_raiser = seat
        else:
            inc = 0
            st["pending"].discard(seat)
        if inc:
            invested[seat] = invested.get(seat, 0) + inc

    if target_street == 0 and st["current_bet"] <= BIG_BLIND:
        current_n_raises = 0
        current_last_raiser = None
    return current_segment, invested, min(current_n_raises, 4), current_last_raiser, st["last_full_raise"]


def current_street_aggression(log, players, current_bet, street_name):
    """(n_raises, last_raiser, last_full_raise) for the current street."""
    blind_only = street_name == "preflop" and current_bet <= 100
    if current_bet <= 0 or blind_only:
        return 0, None, BIG_BLIND
    if any(entry.get("action") == "deal" for entry in log):
        n_raises = 0
        last_raiser = None
        street_current_bet = 0
        last_full_raise = BIG_BLIND
        for entry in _street_action_segment(log):
            action = entry.get("action")
            if entry.get("seat") is None:
                continue
            seat = int(entry["seat"])
            amount = _safe_int(entry.get("amount", 0))
            if action in ("small_blind", "big_blind", "call"):
                street_current_bet = max(street_current_bet, amount)
                continue
            if action not in ("raise", "all_in"):
                continue
            raise_size = max(0, amount - street_current_bet)
            street_current_bet = max(street_current_bet, amount)
            if raise_size >= last_full_raise:
                last_full_raise = raise_size
                n_raises += 1
                last_raiser = seat
        if n_raises:
            return min(n_raises, 4), last_raiser, last_full_raise
        return 1, None, BIG_BLIND
    _, _, n_raises, last_raiser, last_full_raise = _replay_betting_rounds(log, players, street_name)
    if n_raises:
        return n_raises, last_raiser, last_full_raise
    return 1, None, BIG_BLIND


def _hand_invested_from_log(log, players, street_name):
    if players is not None and not any(entry.get("action") == "deal" for entry in log):
        return _replay_betting_rounds(log, players, street_name)[1]
    invested = {}
    street_bets = {}
    for entry in log:
        action = entry.get("action")
        if action == "deal":
            street_bets.clear()
            continue
        if entry.get("seat") is None:
            continue
        seat = int(entry["seat"])
        amount = max(_safe_int(entry.get("amount", 0)), 0)
        if action in ("small_blind", "big_blind", "call"):
            inc = amount
            street_bets[seat] = street_bets.get(seat, 0) + inc
        elif action in ("raise", "all_in"):
            inc = max(0, amount - street_bets.get(seat, 0))
            street_bets[seat] = max(street_bets.get(seat, 0), amount)
        else:
            inc = 0
        if inc:
            invested[seat] = invested.get(seat, 0) + inc
    return invested


def _count_straight_out_ranks(rank_present):
    out_ranks = set()
    for start in range(9):
        missing = [r for r in range(start, start + 5) if not rank_present[r]]
        if len(missing) == 1:
            out_ranks.update(missing)
    wheel = [12, 0, 1, 2, 3]
    if sum(1 for r in wheel if rank_present[r]) == 4:
        out_ranks.update(r for r in wheel if not rank_present[r])
    return len(out_ranks)


def _detect_draws(hole, board, street):
    if street >= 3 or not board:
        return False, False, False, 0, False
    all_cards = hole + board
    suit_counts = [0, 0, 0, 0]
    for c in all_cards:
        suit_counts[c // 13] += 1
    max_suit_count = max(suit_counts)
    flush_draw = max_suit_count == 4
    flush_suit = suit_counts.index(max_suit_count) if flush_draw else -1
    nut_flush_draw = False
    if flush_draw:
        on_board = [c % 13 for c in board if c // 13 == flush_suit]
        in_hand = [c % 13 for c in hole if c // 13 == flush_suit]
        if in_hand:
            nut_flush_draw = max(in_hand) == max(on_board + in_hand)
    rank_present = [False] * 13
    for c in all_cards:
        rank_present[c % 13] = True
    outs_ranks = _count_straight_out_ranks(rank_present)
    overlap = min(outs_ranks, 2) if flush_draw and outs_ranks > 0 else 0
    draw_outs = (9 if flush_draw else 0) + outs_ranks * 4 - overlap
    return flush_draw, outs_ranks >= 2, outs_ranks == 1, draw_outs, nut_flush_draw


def _board_texture(board):
    if not board:
        return False, False, 0.0, False
    ranks = [c % 13 for c in board]
    suits = [c // 13 for c in board]
    paired = len(set(ranks)) < len(ranks)
    monotone = len(set(suits)) == 1
    n = len(ranks)
    if n < 2:
        wet = 0.0
    else:
        close = total = 0
        for i in range(n):
            for j in range(i + 1, n):
                total += 1
                if abs(ranks[i] - ranks[j]) <= 2:
                    close += 1
        wet = close / total
    rank_present = [False] * 13
    for r in ranks:
        rank_present[r] = True
    straight_possible = any(sum(1 for r in range(s, s + 5) if rank_present[r]) >= 3 for s in range(9))
    if not straight_possible:
        straight_possible = sum(1 for r in (12, 0, 1, 2, 3) if rank_present[r]) >= 3
    return paired, monotone, wet, straight_possible


def compute_legal_mask(state, n_raises=0, last_full_raise=BIG_BLIND):
    legal = [False] * N_ACTIONS
    owed = state.get("amount_owed", 0)
    stack = state.get("your_stack", 0)
    pot = state.get("pot", 0)
    min_raise = state.get("min_raise_to", 0)
    players = state.get("players", [])
    my_seat = state.get("seat_to_act", 0)
    last_full_raise = max(_safe_int(last_full_raise, BIG_BLIND), BIG_BLIND)
    if owed > 0:
        legal[0] = True
    legal[1] = True
    if stack > owed and min_raise > 0:
        pot_after_call = pot + owed
        bet_room = stack - owed
        bet_50 = round(0.50 * pot_after_call)
        if bet_50 >= last_full_raise and bet_room > bet_50:
            legal[2] = True
        if pot_after_call >= last_full_raise and bet_room > pot_after_call:
            legal[3] = True
        opp = [p.get("stack", 0) for p in players if p.get("seat") != my_seat and not p.get("is_folded")]
        max_opp = max(opp) if opp else 0
        eff_stack = min(stack, max_opp) if max_opp > 0 else stack
        if eff_stack / max(pot, 1) < 4:
            legal[4] = True
    return legal


def encode_state(state, preflop):
    """preflop = (paired[13], suited[13][13], offsuit[13][13]) equity tables."""
    paired_eq, suited_eq, offsuit_eq = preflop
    f = [0.0] * FEATURE_DIM
    my_cards = state["your_cards"]
    community = state.get("community_cards", [])
    players = state.get("players", [])
    my_seat = state["seat_to_act"]
    n_players = len(players)
    dealer = infer_dealer(state, n_players)
    street_name = state.get("street", "preflop")
    street = {"preflop": 0, "flop": 1, "turn": 2, "river": 3}[street_name]
    pot = state.get("pot", 0)
    my_stack = state.get("your_stack", STARTING_STACK)
    to_call = state.get("amount_owed", 0)
    current_bet = state.get("current_bet", 0)

    c0, c1 = card_index(my_cards[0]), card_index(my_cards[1])
    r0, r1, s0, s1 = c0 % 13, c1 % 13, c0 // 13, c1 // 13
    hi, lo = max(r0, r1), min(r0, r1)
    board = [card_index(c) for c in community]

    f[0] = paired_eq[r0] if r0 == r1 else (suited_eq[hi][lo] if s0 == s1 else offsuit_eq[hi][lo])
    if street > 0 and community:
        f[1] = evaluate([c0, c1] + board) / MAX_EVAL7_SCORE
    fd, oesd, gs, outs, nfd = _detect_draws([c0, c1], board, street)
    f[2], f[3], f[4], f[5], f[6] = float(fd), float(oesd), float(gs), outs / 20.0, float(nfd)
    f[7], f[8] = hi / 12.0, lo / 12.0
    f[9], f[10] = float(s0 == s1), float(r0 == r1)
    f[11] = (hi - lo - 1) / 12.0 if hi != lo else 0.0
    if board:
        bp, bm, bw, sp = _board_texture(board)
        f[12], f[13] = float(bp), float(bm)
        f[14] = sum(1 for b in board if b % 13 > hi) / 5.0
        f[15], f[16] = bw, float(sp)

    f[17 + street] = 1.0
    f[21 + min((my_seat - dealer) % max(n_players, 2), 5)] = 1.0
    f[27] = pot / STARTING_STACK
    f[28] = my_stack / STARTING_STACK
    active_stacks = [p.get("stack", 0) for p in players if not p.get("is_folded")]
    spr = (min(active_stacks) if active_stacks else 0) / max(pot, 1)
    f[29] = min(max(spr, 0.0), 10.0) / 10.0
    f[30] = to_call / (pot + to_call) if to_call > 0 and (pot + to_call) > 0 else 0.0
    opp_stacks = sorted((p.get("stack", 0) for p in players
                         if p.get("seat") != my_seat and not p.get("is_folded")), reverse=True)
    for i, s in enumerate(opp_stacks[:5]):
        f[31 + i] = s / STARTING_STACK

    log = state.get("action_log") or []
    n_raises, last_raiser, last_full_raise = current_street_aggression(log, players, current_bet, street_name)
    has_aggressor = last_raiser is not None or (
        current_bet > 0 and not (street_name == "preflop" and current_bet <= 100))
    f[36] = min(n_raises, 4) / 4.0
    f[37] = float(has_aggressor)
    f[38] = float(last_raiser == my_seat)
    f[39] = state.get("your_bet_this_street", 0) / STARTING_STACK
    hand_invested = _hand_invested_from_log(log, players, street_name)
    invested = hand_invested.get(my_seat, 0) if hand_invested else STARTING_STACK - my_stack
    f[40] = invested / STARTING_STACK
    f[41] = current_bet / max(pot, 1)
    f[42] = to_call / max(my_stack, 1)
    max_vill_bets = max_vill_invested = 0
    for p in players:
        if p.get("seat") != my_seat and not p.get("is_folded"):
            max_vill_bets = max(max_vill_bets, _safe_int(p.get("bet_this_street", 0)))
            seat = _safe_int(p.get("seat", -1), -1)
            vi = hand_invested.get(seat, 0) if hand_invested else STARTING_STACK - p.get("stack", STARTING_STACK)
            max_vill_invested = max(max_vill_invested, vi)
    f[43] = max_vill_bets / STARTING_STACK
    f[44] = max_vill_invested / STARTING_STACK
    f[45] = sum(1 for p in players if not p.get("is_folded")) / 6.0

    legal = compute_legal_mask(state, n_raises, last_full_raise)
    for a in range(N_ACTIONS):
        f[LEGAL_MASK_OFFSET + a] = float(legal[a])
    return f, legal
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/advit_lite_tests/test_features.py -v`
Expected: 2 passed (the recorded-states test takes about 10 s)

- [ ] **Step 5: Commit**

```bash
git add arena/src/advit_lite/features.py arena/tests/advit_lite_tests/conftest.py arena/tests/advit_lite_tests/test_features.py
git commit -m "Port advitrocks9's feature encoder to plain Python, checked against the original"
```

---

### Task 3: Network and policy port

**Files:**
- Create: `arena/src/advit_lite/network.py`
- Create: `arena/src/advit_lite/policy.py`
- Test: `arena/tests/advit_lite_tests/test_network_policy.py`

**Interfaces:**
- Consumes: `encode_state`, `infer_dealer`, `BIG_BLIND` (Task 2).
- Produces:
  - `advit_lite.network.LAYER_ORDER: tuple[str, ...]` (16 tensor names, blob order)
  - `advit_lite.network.decode_weights(blob: str, meta: list[tuple[str, tuple[int, ...], float]]) -> dict` (used in Task 4)
  - `advit_lite.network.strategy(model: dict, features: list[float], legal: list[bool]) -> list[float]` — `model` maps each name in `LAYER_ORDER` to a list (1-D) or list of rows (2-D)
  - `advit_lite.policy.decide(state: dict, model: dict, preflop: tuple, rng: random.Random) -> dict` — a Fullhouse action `{"action": "fold"|"check"|"call"|"raise"|"all_in", "amount"?: int}`
  - `advit_lite.policy.push_fold(state) -> dict | None`, `advit_lite.policy.to_engine_action(action_id: int, state) -> dict`

- [ ] **Step 1: Write the failing test**

Create `arena/tests/advit_lite_tests/test_network_policy.py`:

```python
import random

import numpy as np
import pytest

from advit_lite import network, policy
from advit_lite.features import encode_state


@pytest.fixture(scope="module")
def float_model(advit_dir):
    raw = np.load(advit_dir / "data" / "deep_cfr_model.npz")
    return {k: raw[k].astype(np.float64).tolist() for k in raw.files}


def test_network_matches_the_original(fullhouse_states, preflop_tables, float_model, advit_dir):
    from bot.deep_cfr_lookup import DeepCFRLookup  # the original, numpy

    lookup = DeepCFRLookup(str(advit_dir / "data" / "deep_cfr_model.npz"))
    for state in fullhouse_states[::5]:
        features, legal = encode_state(state, preflop_tables)
        ours = network.strategy(float_model, features, legal)
        theirs = lookup.get_strategy(state)
        assert abs(sum(ours) - 1.0) < 1e-9
        assert 0.5 * np.abs(np.asarray(ours) - theirs).sum() < 1e-4, state


def test_push_fold_matches_the_original_up_to_six_players(fullhouse_states, advit_dir):
    import bot.bot as original  # loads the original model; needs numpy and eval7

    checked = 0
    for state in fullhouse_states:
        if state["street"] != "preflop":
            continue
        if len(state["players"]) <= 6:
            assert policy.push_fold(state) == original._push_fold(state), state
            checked += 1
        else:
            policy.push_fold(state)  # the original raises IndexError at seats 7-8; ours must not
    assert checked > 500


def test_engine_actions_match_the_original(fullhouse_states, advit_dir):
    import bot.bot as original

    for state in fullhouse_states[::3]:
        for action_id in range(5):
            assert policy.to_engine_action(action_id, state) == original._to_engine_action(action_id, state)


def test_decide_always_returns_an_engine_action(fullhouse_states, preflop_tables, float_model):
    rng = random.Random(0)
    for state in fullhouse_states[::4]:
        action = policy.decide(state, float_model, preflop_tables, rng)
        assert action["action"] in ("fold", "check", "call", "raise", "all_in")
        if action["action"] == "raise":
            assert state["min_raise_to"] <= action["amount"] < state["your_bet_this_street"] + state["your_stack"]


def test_decide_falls_back_safely_on_a_broken_state(preflop_tables, float_model):
    broken = {"street": "flop", "can_check": True}
    assert policy.decide(broken, float_model, preflop_tables, random.Random(0)) == {"action": "check"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/advit_lite_tests/test_network_policy.py -v`
Expected: FAIL with `ImportError: cannot import name 'network' from 'advit_lite'`

- [ ] **Step 3: Write the network**

Create `arena/src/advit_lite/network.py`:

```python
"""advitrocks9's Deep CFR advantage network in plain Python, with 8-bit weights.

Weights travel as BLOB (base85 of zlib-compressed int8 bytes) plus META, a list of
(name, shape, scale) in blob order: weight = int8 value * scale.
"""

import base64
import math
import zlib
from array import array
from operator import mul

LAYER_ORDER = (
    "trunk_w0", "trunk_b0", "trunk_ln0_g", "trunk_ln0_b",
    "trunk_w1", "trunk_b1", "trunk_ln1_g", "trunk_ln1_b",
    "val_w0", "val_b0", "val_w1", "val_b1",
    "adv_w0", "adv_b0", "adv_w1", "adv_b1",
)


def decode_weights(blob, meta):
    raw = array("b", zlib.decompress(base64.b85decode(blob)))
    model = {}
    pos = 0
    for name, shape, scale in meta:
        size = 1
        for dim in shape:
            size *= dim
        flat = [v * scale for v in raw[pos:pos + size]]
        pos += size
        if len(shape) == 2:
            cols = shape[1]
            model[name] = [flat[r * cols:(r + 1) * cols] for r in range(shape[0])]
        else:
            model[name] = flat
    if pos != len(raw):
        raise ValueError("weights blob has %d unused bytes" % (len(raw) - pos))
    return model


def _linear(x, weight, bias):
    return [sum(map(mul, row, x)) + b for row, b in zip(weight, bias)]


def _leaky_relu(x):
    return [v if v > 0 else 0.01 * v for v in x]


def _layer_norm(x, gamma, beta):
    mean = sum(x) / len(x)
    var = sum((v - mean) ** 2 for v in x) / len(x)
    inv = 1.0 / math.sqrt(var + 1e-5)
    return [g * (v - mean) * inv + b for v, g, b in zip(x, gamma, beta)]


def strategy(model, features, legal):
    """Probabilities over (fold, check/call, bet half pot, bet pot, all-in), legal actions only."""
    m = model
    h = _leaky_relu(_layer_norm(_linear(features, m["trunk_w0"], m["trunk_b0"]), m["trunk_ln0_g"], m["trunk_ln0_b"]))
    h = _leaky_relu(_layer_norm(_linear(h, m["trunk_w1"], m["trunk_b1"]), m["trunk_ln1_g"], m["trunk_ln1_b"]))
    value = _linear(_leaky_relu(_linear(h, m["val_w0"], m["val_b0"])), m["val_w1"], m["val_b1"])[0]
    adv = _linear(_leaky_relu(_linear(h, m["adv_w0"], m["adv_b0"])), m["adv_w1"], m["adv_b1"])
    legal_f = [1.0 if ok else 0.0 for ok in legal]
    n_legal = sum(legal_f)
    if n_legal <= 0:
        raise ValueError("no legal actions")
    masked = [a * l for a, l in zip(adv, legal_f)]
    mean = sum(masked) / n_legal
    regrets = [max((value + a - mean * l) * l, 0.0) * l for a, l in zip(masked, legal_f)]
    total = sum(regrets)
    if total > 0:
        return [r / total for r in regrets]
    return [l / n_legal for l in legal_f]
```

- [ ] **Step 4: Write the policy**

Create `arena/src/advit_lite/policy.py`:

```python
"""advitrocks9's decide(): short-stack push/fold, then the network, then an engine action.

Works in Fullhouse units (100-chip big blind) on a Fullhouse-format game_state, exactly
like the original bot/bot.py, except that seats 7-8 at 7-8-player tables count as "CO"
(the original raised IndexError there and fell back to check/call).
"""

from advit_lite.features import BIG_BLIND, encode_state, infer_dealer
from advit_lite.network import strategy

FOLD, CHECK_CALL, BET_50, BET_POT, ALL_IN = range(5)
_RANK_VAL = {r: i for i, r in enumerate("23456789TJQKA")}
_POSITIONS_6MAX = ("BTN", "SB", "BB", "LJ", "HJ", "CO")

_PF_TIER1 = set("AA KK QQ JJ TT 99 88 77 AKs AKo AQs AQo AJs ATs AJo KQs KJs KQo ATo A9s A8s A7s "
                "A6s A5s A4s A3s A2s".split())
_PF_TIER2 = _PF_TIER1 | set("66 55 44 33 22 KTs K9s K8s QJs QTs Q9s JTs J9s T9s T8s 98s 87s 76s KJo KTo "
                            "QJo QTo JTo A9o A8o".split())
_PF_TIER3 = _PF_TIER2 | set("K7s K6s K5s K4s K3s K2s Q8s Q7s Q6s J8s J7s T7s 97s 86s 75s 65s 54s K9o K8o "
                            "Q9o J9o T9o 98o 87o A7o A6o A5o A4o A3o A2o".split())
_PF_CALL_TIGHT = set("AA KK QQ JJ TT 99 88 77 AKs AKo AQs AQo AJs ATs A9s KQs KJs KTs QJs".split())
_PF_CALL_MEDIUM = _PF_CALL_TIGHT | set("66 55 44 AJo ATo A8s A7s A6s A5s KQo KJo QTs JTs T9s".split())
_PF_CALL_WIDE = _PF_CALL_MEDIUM | set("33 22 A4s A3s A2s K9s QJo Q9s J9s A9o A8o A7o".split())


def hand_class(cards):
    r0, s0, r1, s1 = cards[0][0], cards[0][1], cards[1][0], cards[1][1]
    if _RANK_VAL[r0] < _RANK_VAL[r1]:
        r0, r1, s0, s1 = r1, r0, s1, s0
    if r0 == r1:
        return r0 + r1
    return r0 + r1 + ("s" if s0 == s1 else "o")


def position(state):
    n = len(state.get("players", []))
    offset = (state["seat_to_act"] - infer_dealer(state, max(n, 2))) % max(n, 2)
    if n == 2:
        return "BTN" if offset == 0 else "BB"
    if n == 3:
        return ("BTN", "SB", "BB")[offset]
    if n == 4:
        return ("BTN", "SB", "BB", "CO")[offset]
    if n == 5:
        return ("BTN", "SB", "BB", "HJ", "CO")[offset]
    return _POSITIONS_6MAX[offset] if offset < 6 else "CO"


def push_fold(state):
    stack = state["your_stack"]
    me = state["seat_to_act"]
    max_opp = max((p.get("stack", 0) or 0 for p in state.get("players", [])
                   if p.get("seat") != me and not p.get("is_folded")), default=stack)
    eff_bb = min(stack, max_opp) / BIG_BLIND
    if eff_bb > 12:
        return None
    hclass = hand_class(state["your_cards"])
    owed = state.get("amount_owed", 0)
    if owed > 0:
        pot_odds = owed / (state["pot"] + owed) if state["pot"] + owed > 0 else 1.0
        if hclass in _PF_TIER1:
            return {"action": "all_in"}
        if eff_bb <= 6:
            call_range = _PF_CALL_MEDIUM if pot_odds < 0.35 else _PF_CALL_TIGHT
        elif eff_bb <= 10:
            call_range = _PF_CALL_WIDE if pot_odds < 0.35 else _PF_CALL_MEDIUM
        else:
            call_range = _PF_CALL_WIDE
        return {"action": "call"} if hclass in call_range else {"action": "fold"}
    pos = position(state)
    push_range = (_PF_TIER1 if pos in ("LJ", "HJ") else _PF_TIER2 if pos == "CO"
                  else _PF_TIER3 if pos in ("BTN", "SB") else _PF_CALL_WIDE)
    if hclass in push_range:
        return {"action": "all_in"}
    return {"action": "check"} if state.get("can_check", False) else {"action": "fold"}


def to_engine_action(action_id, state):
    if action_id == FOLD:
        return {"action": "check"} if state.get("can_check") else {"action": "fold"}
    if action_id == CHECK_CALL:
        return {"action": "check"} if state.get("can_check") else {"action": "call"}
    if action_id == ALL_IN:
        return {"action": "all_in"}
    frac = 0.5 if action_id == BET_50 else 1.0
    pot = state.get("pot", 0)
    my_bet = state.get("your_bet_this_street", 0)
    to_call = state.get("amount_owed", 0)
    stack = state.get("your_stack", 0)
    raise_to = my_bet + to_call + int(round(frac * (pot + to_call)))
    max_raise = my_bet + stack
    raise_to = max(state.get("min_raise_to", 0), min(raise_to, max_raise))
    if raise_to >= max_raise:
        return {"action": "all_in"}
    if raise_to <= my_bet + to_call:
        return {"action": "call"} if to_call > 0 else {"action": "check"}
    return {"action": "raise", "amount": raise_to}


def sample(probs, rng):
    r = rng.random()
    cumulative = 0.0
    for i, p in enumerate(probs):
        cumulative += p
        if r < cumulative:
            return i
    return len(probs) - 1


def safe_default(state):
    if state.get("can_check", False):
        return {"action": "check"}
    if state.get("amount_owed", 0) > 0 and state.get("your_stack", 0) > 0:
        return {"action": "call"}
    return {"action": "fold"}


def decide(state, model, preflop, rng):
    try:
        if state.get("street", "preflop") == "preflop":
            pf = push_fold(state)
            if pf is not None:
                return pf
        features, legal = encode_state(state, preflop)
        return to_engine_action(sample(strategy(model, features, legal), rng), state)
    except Exception:
        return safe_default(state)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/advit_lite_tests/test_network_policy.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add arena/src/advit_lite/network.py arena/src/advit_lite/policy.py arena/tests/advit_lite_tests/test_network_policy.py
git commit -m "Port advitrocks9's network and decision policy to plain Python"
```

---

### Task 4: Quantize the weights and build the single-file bot

**Files:**
- Create: `arena/tools/build_advit_lite.py`
- Generated (committed): `arena/src/advit_lite/weights_data.py`
- Generated (not committed): `arena/dist/advit_lite/bot.py`
- Modify: `arena/.gitignore` (add `dist/`)
- Test: `arena/tests/advit_lite_tests/test_build.py`

**Interfaces:**
- Consumes: `network.LAYER_ORDER`, `network.decode_weights`, `network.strategy` (Task 3); `features.encode_state` (Task 2).
- Produces:
  - `advit_lite.weights_data.BLOB: str`, `META: list[tuple[str, tuple[int, ...], float]]`, `PREFLOP: tuple` (same shape as the `preflop_tables` fixture).
  - `arena/dist/advit_lite/bot.py` once Task 5's modules exist (`BUNDLE_ORDER` names them); this task's test checks only the weights.

- [ ] **Step 1: Write the failing test**

Create `arena/tests/advit_lite_tests/test_build.py`:

```python
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from advit_lite.features import encode_state

ARENA = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def weights_data():
    subprocess.run([sys.executable, str(ARENA / "tools" / "build_advit_lite.py"), "--weights-only"], check=True)
    import importlib

    import advit_lite.weights_data as data
    return importlib.reload(data)


def test_weights_round_trip_within_half_a_step(weights_data, advit_dir):
    from advit_lite.network import decode_weights

    model = decode_weights(weights_data.BLOB, weights_data.META)
    raw = np.load(advit_dir / "data" / "deep_cfr_model.npz")
    for name, shape, scale in weights_data.META:
        assert np.asarray(model[name]).shape == shape
        assert np.abs(np.asarray(model[name]) - raw[name]).max() <= scale / 2 + 1e-9


def test_int8_network_plays_like_the_original(weights_data, fullhouse_states, advit_dir):
    from bot.deep_cfr_lookup import DeepCFRLookup
    from advit_lite.network import decode_weights, strategy

    model = decode_weights(weights_data.BLOB, weights_data.META)
    lookup = DeepCFRLookup(str(advit_dir / "data" / "deep_cfr_model.npz"))
    shifts, same_top = [], 0
    for state in fullhouse_states:
        theirs = lookup.get_strategy(state)
        ours = strategy(model, *encode_state(state, weights_data.PREFLOP))
        shifts.append(0.5 * np.abs(np.asarray(ours) - theirs).sum())
        same_top += int(np.argmax(ours)) == int(np.argmax(theirs))
    assert np.mean(shifts) < 0.03          # measured 0.019 while planning
    assert same_top / len(fullhouse_states) > 0.97  # measured 98.3%


def test_preflop_tables_are_the_originals(weights_data, preflop_tables):
    assert weights_data.PREFLOP == preflop_tables
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/advit_lite_tests/test_build.py -v`
Expected: FAIL (`build_advit_lite.py` does not exist: `CalledProcessError`)

- [ ] **Step 3: Write the build script**

Create `arena/tools/build_advit_lite.py`:

```python
"""Build the submission: quantize advitrocks9's weights, write weights_data.py, bundle one bot.py.

Usage (from arena/):  uv run python tools/build_advit_lite.py [--weights-only]
Reads  bots/advitrocks9/data/{deep_cfr_model,preflop_equity}.npz   (numpy: build time only)
Writes src/advit_lite/weights_data.py and dist/advit_lite/bot.py, and prints the bot's size.
"""

import base64
import re
import sys
import zlib
from pathlib import Path

import numpy as np

ARENA = Path(__file__).resolve().parents[1]
PACKAGE = ARENA / "src" / "advit_lite"
MODEL_NPZ = ARENA / "bots" / "advitrocks9" / "data" / "deep_cfr_model.npz"
PREFLOP_NPZ = ARENA / "bots" / "advitrocks9" / "data" / "preflop_equity.npz"
OUT = ARENA / "dist" / "advit_lite" / "bot.py"
BUNDLE_ORDER = ("hand_eval", "features", "network", "policy", "kit_adapter", "weights_data", "agent")
SIZE_LIMIT = 200_000  # bytes; the organisers' "200 KB", read conservatively

sys.path.insert(0, str(ARENA / "src"))
from advit_lite.network import LAYER_ORDER  # noqa: E402


def quantize(npz_path):
    """int8 per tensor: scale = max|w| / 127. Returns (blob, meta)."""
    data = np.load(npz_path)
    raw = b""
    meta = []
    for name in LAYER_ORDER:
        w = data[name].astype(np.float64)
        scale = float(np.abs(w).max()) / 127.0 or 1.0
        raw += np.clip(np.round(w / scale), -127, 127).astype(np.int8).tobytes()
        meta.append((name, tuple(int(d) for d in w.shape), scale))
    return base64.b85encode(zlib.compress(raw, 9)).decode("ascii"), meta


def preflop_tables(npz_path):
    data = np.load(npz_path)
    paired = [float(x) for x in data["paired"]]
    suited = [[float(x) for x in row] for row in data["suited"]]
    offsuit = [[float(x) for x in row] for row in data["offsuit"]]
    return paired, suited, offsuit


def write_weights_data():
    blob, meta = quantize(MODEL_NPZ)
    preflop = preflop_tables(PREFLOP_NPZ)
    text = (
        '"""Generated by tools/build_advit_lite.py from advitrocks9\'s model. Do not edit."""\n\n'
        f"META = {meta!r}\n\n"
        f"PREFLOP = {preflop!r}\n\n"
        f"BLOB = {blob!r}\n"
    )
    (PACKAGE / "weights_data.py").write_text(text, encoding="utf-8")


def bundle():
    """Concatenate the package into one file, dropping its internal imports."""
    parts = ['"""advit_lite: advitrocks9 (MIT, Copyright (c) 2026 Advit Arora) converted to the AlgoSoc rules. '
             'Generated by tools/build_advit_lite.py; do not edit."""\n']
    for name in BUNDLE_ORDER:
        source = (PACKAGE / f"{name}.py").read_text(encoding="utf-8")
        source = re.sub(r"^from advit_lite[^\n]*\n", "", source, flags=re.M)
        parts.append(f"\n# ===== {name}.py =====\n{source}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(parts), encoding="utf-8")
    return OUT.stat().st_size


if __name__ == "__main__":
    write_weights_data()
    if "--weights-only" in sys.argv:
        sys.exit(0)
    size = bundle()
    print(f"{OUT}: {size:,} bytes ({size / 1024:.1f} KiB), limit {SIZE_LIMIT:,}")
    sys.exit(0 if size <= SIZE_LIMIT else 1)
```

Append to `arena/.gitignore`:

```
dist/
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/advit_lite_tests/test_build.py -v`
Expected: 3 passed. `src/advit_lite/weights_data.py` now exists (about 139 KB).

- [ ] **Step 5: Commit**

```bash
git add arena/tools/build_advit_lite.py arena/src/advit_lite/weights_data.py arena/.gitignore arena/tests/advit_lite_tests/test_build.py
git commit -m "Quantize advitrocks9's weights to 8 bits and add the advit_lite build script"
```

---

### Task 5: AlgoSoc adapter, Agent and the bundled bot.py

**Files:**
- Create: `arena/src/advit_lite/kit_adapter.py`
- Create: `arena/src/advit_lite/agent.py`
- Test: `arena/tests/advit_lite_tests/test_agent.py`

**Interfaces:**
- Consumes: `policy.decide` (Task 3), `network.decode_weights` (Task 3), `weights_data.BLOB/META/PREFLOP` (Task 4); fixture `kit_states` (Task 2).
- Produces:
  - `advit_lite.kit_adapter.to_fullhouse(state: dict) -> tuple[dict, float]` — Fullhouse game_state and chip scale `k`
  - `advit_lite.kit_adapter.to_kit(action: dict, state: dict, k: float) -> dict` — always legal for the kit state
  - `advit_lite.kit_adapter.seats_in_hand(state: dict) -> list[int]`
  - `advit_lite.agent.Agent` with `on_table_start(info)`, `act(state) -> dict`, `on_hand_end(summary)`
  - `arena/dist/advit_lite/bot.py` (built by `tools/build_advit_lite.py`)

- [ ] **Step 1: Write the failing test**

Create `arena/tests/advit_lite_tests/test_agent.py`:

```python
import ast
import subprocess
import sys
import time
from pathlib import Path

from advit_lite.kit_adapter import seats_in_hand, to_fullhouse, to_kit

ARENA = Path(__file__).resolve().parents[2]
BUNDLE = ARENA / "dist" / "advit_lite" / "bot.py"
STDLIB = set(sys.stdlib_module_names)


def kit_state_with_busted_seats():
    """8-seat sit-and-go: seats 2 and 5 are busted; blinds 50/100; seat 4 to act facing a raise."""
    return {
        "hand_number": 40, "street": "preflop", "seat": 4, "button": 1,
        "hole_cards": ["As", "Kd"], "board": [], "small_blind": 50, "big_blind": 100,
        "pot": 450, "stacks": [3000, 2900, 0, 1950, 4000, 0, 2500, 1700],
        "bets": [0, 0, 0, 100, 0, 0, 300, 0],
        "folded": [True, False, True, False, False, True, False, False],
        "to_call": 300, "min_raise_to": 500, "max_raise_to": 4000,
        "legal_actions": ["fold", "call", "raise"],
        "history": [
            {"seat": 7, "street": "preflop", "action": "small_blind", "amount": 50},
            {"seat": 3, "street": "preflop", "action": "big_blind", "amount": 100},
            {"seat": 0, "street": "preflop", "action": "fold", "amount": 0},
            {"seat": 6, "street": "preflop", "action": "raise", "amount": 300},
        ],
    }


def test_busted_seats_are_dropped_and_chips_rescaled():
    state = kit_state_with_busted_seats()
    assert seats_in_hand(state) == [0, 1, 3, 4, 6, 7]
    fh, k = to_fullhouse(state)
    assert k == 1.0  # big blind 100 -> Fullhouse's 100
    assert fh["seat_to_act"] == 3  # seat 4 is the 4th seat in hand
    assert [p["seat"] for p in fh["players"]] == [0, 1, 2, 3, 4, 5]
    assert fh["players"][0]["is_folded"] and not fh["players"][1]["is_folded"]
    assert fh["amount_owed"] == 300 and fh["min_raise_to"] == 500 and fh["current_bet"] == 300
    assert fh["action_log"][0] == {"seat": 5, "action": "small_blind", "amount": 50}

    state["big_blind"], state["small_blind"] = 20, 10
    fh, k = to_fullhouse(state)
    assert k == 5.0 and fh["your_stack"] == 20000 and fh["amount_owed"] == 1500


def test_actions_come_back_legal_and_in_kit_chips():
    state = kit_state_with_busted_seats()
    assert to_kit({"action": "raise", "amount": 1200}, state, 2.0) == {"action": "raise", "amount": 600}
    assert to_kit({"action": "raise", "amount": 99999}, state, 1.0) == {"action": "raise", "amount": 4000}
    assert to_kit({"action": "raise", "amount": 10}, state, 1.0) == {"action": "raise", "amount": 500}
    assert to_kit({"action": "all_in"}, state, 1.0) == {"action": "all_in"}
    assert to_kit({"action": "check"}, state, 1.0) == {"action": "call"}
    assert to_kit({"action": "fold"}, state, 1.0) == {"action": "fold"}
    no_raise = dict(state, legal_actions=["fold", "call"], min_raise_to=None, max_raise_to=None)
    assert to_kit({"action": "raise", "amount": 900}, no_raise, 1.0) == {"action": "call"}
    free = dict(state, to_call=0, legal_actions=["check", "raise"])
    assert to_kit({"action": "fold"}, free, 1.0) == {"action": "check"}


def test_agent_answers_every_recorded_state_legally_and_fast(kit_states):
    from advit_lite.agent import Agent

    agent = Agent()
    agent.on_table_start({"seat": 0})
    timings = []
    for state in kit_states:
        start = time.perf_counter()
        action = agent.act(state)
        timings.append(time.perf_counter() - start)
        kind = action["action"]
        assert kind in ("fold", "check", "call", "raise", "all_in")
        if kind in ("fold", "check", "call", "raise"):
            assert kind in state["legal_actions"], (kind, state["legal_actions"])
        if action["action"] == "raise":
            assert state["min_raise_to"] <= action["amount"] <= state["max_raise_to"]
    timings.sort()
    assert timings[len(timings) // 2] < 0.005  # median under 5 ms (measured about 4 ms)
    assert timings[int(len(timings) * 0.99)] < 0.009  # 99th percentile under 9 ms (measured 7.0-7.4 ms)


def test_bundle_is_one_stdlib_file_under_200kb():
    result = subprocess.run([sys.executable, str(ARENA / "tools" / "build_advit_lite.py")],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert BUNDLE.stat().st_size <= 200_000
    tree = ast.parse(BUNDLE.read_text(encoding="utf-8"))
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imported <= STDLIB, imported - STDLIB
    assert "advit_lite" not in imported


def test_bundle_runs_in_a_clean_interpreter():
    script = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('bot', r'{BUNDLE}')\n"
        "bot = importlib.util.module_from_spec(spec); spec.loader.exec_module(bot)\n"
        "a = bot.Agent(); a.on_table_start({'seat': 4})\n"
        "s = {'hand_number': 1, 'street': 'preflop', 'seat': 1, 'button': 1, 'hole_cards': ['As', 'Ad'],\n"
        "     'board': [], 'small_blind': 10, 'big_blind': 20, 'pot': 30, 'stacks': [1980, 1990],\n"
        "     'bets': [20, 10], 'folded': [False, False], 'to_call': 10, 'min_raise_to': 40,\n"
        "     'max_raise_to': 2000, 'legal_actions': ['fold', 'call', 'raise'],\n"
        "     'history': [{'seat': 1, 'street': 'preflop', 'action': 'small_blind', 'amount': 10},\n"
        "                 {'seat': 0, 'street': 'preflop', 'action': 'big_blind', 'amount': 20}]}\n"
        "print(a.act(s)['action'])\n"
    )
    result = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=BUNDLE.parent)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() in ("raise", "all_in", "call")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/advit_lite_tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'advit_lite.kit_adapter'`

- [ ] **Step 3: Write the adapter**

Create `arena/src/advit_lite/kit_adapter.py`:

```python
"""Translate between the AlgoSoc kit's state/action format and advitrocks9's Fullhouse format.

The kit (8-bot sit-and-gos, 2,000 chips, blinds rising from 10/20) gives every seat at the table,
including busted ones. advitrocks9 was trained on Fullhouse: only seats in the hand, a 100-chip
big blind and 10,000-chip stacks. So: keep only seats dealt into this hand, renumber them 0..n-1
in seat order, and scale chips by 100 / big_blind. Raise amounts are scaled back on the way out.
"""


def seats_in_hand(state):
    """Seats dealt into this hand: anyone not folded, or anyone who acted (folders included)."""
    acted = {h["seat"] for h in state.get("history", [])}
    return sorted(s for s in range(len(state["stacks"])) if not state["folded"][s] or s in acted)


def to_fullhouse(state):
    """Kit state -> (Fullhouse game_state, chip scale k). Fullhouse chips = kit chips * k."""
    k = 100.0 / state["big_blind"]
    seats = seats_in_hand(state)
    index = {seat: i for i, seat in enumerate(seats)}

    def scale(chips):
        return int(round(chips * k))

    players = []
    for seat in seats:
        folded = bool(state["folded"][seat])
        all_in = state["stacks"][seat] == 0 and not folded
        players.append({
            "seat": index[seat],
            "bot_id": str(seat),
            "stack": scale(state["stacks"][seat]),
            "state": "folded" if folded else "all_in" if all_in else "active",
            "is_folded": folded,
            "is_all_in": all_in,
            "bet_this_street": scale(state["bets"][seat]),
            "hole_cards": None,
        })
    log = [{"seat": index[h["seat"]], "action": h["action"], "amount": scale(h.get("amount") or 0)}
           for h in state.get("history", []) if h["seat"] in index]
    me = state["seat"]
    current = max(state["bets"])
    can_raise = "raise" in state["legal_actions"] and state.get("min_raise_to") is not None
    fullhouse = {
        "type": "action_request",
        "hand_id": str(state.get("hand_number", 0)),
        "street": state["street"],
        "seat_to_act": index[me],
        "pot": scale(state["pot"]),
        "community_cards": list(state["board"]),
        "current_bet": scale(current),
        "min_raise_to": scale(state["min_raise_to"]) if can_raise else 0,
        "amount_owed": scale(state["to_call"]),
        "can_check": state["to_call"] == 0,
        "your_cards": list(state["hole_cards"]),
        "your_stack": scale(state["stacks"][me]),
        "your_bet_this_street": scale(state["bets"][me]),
        "players": players,
        "action_log": log,
    }
    return fullhouse, k


def to_kit(action, state, k):
    """Fullhouse action -> kit action, always legal for the kit state."""
    legal = state["legal_actions"]
    kind = action.get("action")
    if kind == "all_in":
        return {"action": "all_in"}
    if kind == "raise" and "raise" in legal:
        amount = int(round(action["amount"] / k))
        return {"action": "raise", "amount": max(state["min_raise_to"], min(amount, state["max_raise_to"]))}
    if kind in ("raise", "call"):
        return {"action": "call"} if "call" in legal else {"action": "check"}
    if kind == "check":  # Fullhouse treats a check while facing a bet as a call
        return {"action": "check"} if "check" in legal else {"action": "call"}
    return {"action": "fold"} if "fold" in legal else {"action": "check"}
```

- [ ] **Step 4: Write the Agent**

Create `arena/src/advit_lite/agent.py`:

```python
"""The AlgoSoc kit entry point: the platform imports Agent from bot.py and calls act(state)."""

import random

from advit_lite.kit_adapter import to_fullhouse, to_kit
from advit_lite.network import decode_weights
from advit_lite.policy import decide
from advit_lite.weights_data import BLOB, META, PREFLOP

MODEL = decode_weights(BLOB, META)


class Agent:
    def __init__(self):
        self.rng = random.Random(0xC0FFEE)

    def on_table_start(self, info):
        pass

    def act(self, state):
        try:
            fullhouse, k = to_fullhouse(state)
            return to_kit(decide(fullhouse, MODEL, PREFLOP, self.rng), state, k)
        except Exception:
            return {"action": "check"} if "check" in state.get("legal_actions", ()) else {"action": "fold"}

    def on_hand_end(self, summary):
        pass
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/advit_lite_tests/test_agent.py -v`
Expected: 5 passed. The build prints `dist/advit_lite/bot.py: about 169,000 bytes`.

- [ ] **Step 6: Commit**

```bash
git add arena/src/advit_lite/kit_adapter.py arena/src/advit_lite/agent.py arena/tests/advit_lite_tests/test_agent.py
git commit -m "Add AlgoSoc adapter and Agent; build advit_lite into one 169 KB stdlib bot.py"
```

---

### Task 6: Prove it in the arena

**Files:**
- Modify: `arena/bots.toml` (add the `advit-lite` entry)
- Modify: `arena/tests/test_candidates.py` (add `"advit-lite"` to `CANDIDATES`)

**Interfaces:**
- Consumes: `arena/dist/advit_lite/bot.py` (Task 5). The arena's `agent` bot type (`arena/src/arena/agent_bot.py`) loads it, feeds it kit-format states and enforces the 10 ms limit.

- [ ] **Step 1: Register the bot and write the failing test**

Append to `arena/bots.toml`:

```toml

# advitrocks9 converted to the AlgoSoc rules: one stdlib bot.py, built by tools/build_advit_lite.py.
[bots.advit-lite]
type = "agent"
path = "dist/advit_lite/bot.py"
time_limit_ms = 10
```

In `arena/tests/test_candidates.py`, change the list to:

```python
CANDIDATES = ["markus", "lucashsu", "txnujk09", "advitrocks9", "treys", "lucashsu-10ms", "advitrocks9-10ms", "advit-lite"]
```

- [ ] **Step 2: Run the test to verify it fails without a build**

Run: `rm -rf dist && uv run pytest tests/test_candidates.py -k advit-lite -v`
Expected: FAIL with `ValueError: no bot file at ...dist/advit_lite/bot.py`

- [ ] **Step 3: Build and run the test to verify it passes**

Run: `uv run python tools/build_advit_lite.py && uv run pytest tests/test_candidates.py -k advit-lite -v`
Expected: the build prints a size under 200,000 bytes; 1 passed (zero errors, zero illegal actions heads-up and 6-max).

- [ ] **Step 4: Heads-up duplicate match against the original**

Run: `uv run arena roundrobin advit-lite advitrocks9-10ms --until-decided --deals 300 --max-deals 3000 --stack 2000 --sb 10 --bb 20`
Expected: no winner declared ("No clear winner after 3000 deals per pair"), with `advit-lite`'s mbb/hand interval containing zero, `errors` 0 and `max ms` under 10 (apart from the first decision of a table). If `advit-lite` loses clearly, the 8-bit weights cost too much: stop and report the numbers; do not tune.

- [ ] **Step 5: Full-table check under the real rules**

Run: `uv run arena table advit-lite advitrocks9-10ms markus txnujk09 treys allin call random --until-decided --deals 50 --max-deals 1000 --stack 2000 --sb 10 --bb 20`
Expected: `advit-lite` and `advitrocks9-10ms` within each other's intervals; `advit-lite` `errors` 0.

- [ ] **Step 6: Commit**

```bash
git add arena/bots.toml arena/tests/test_candidates.py
git commit -m "Register advit-lite in the arena with the 10 ms limit"
```

---

## Done when

- `uv run pytest tests/advit_lite_tests tests/test_candidates.py` passes.
- `uv run python tools/build_advit_lite.py` exits 0 and prints a size ≤ 200,000 bytes.
- The heads-up duplicate match shows no clear difference between `advit-lite` and the original.
- `arena/dist/advit_lite/bot.py` is the file to upload.
