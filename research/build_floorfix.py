"""Rebuild the standalone Floorfix adapter from the preserved MIT source.

Run with Python 3.12+ from any directory. The seeded 169 x 900 equity work is
build-time only. No upstream code is executed except the audited table function.
"""
from pathlib import Path
import ast
import pprint
import random

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research/sources/fullhouse_floorfix.py"
OUTPUT = ROOT / "candidates/imported/fullhouse_floorfix.py"

# Independent evaluator: suit bitsets and repeated-rank bitsets, not the
# organizer's histogram/group implementation. Scores are packed lexicographic
# (category, up to five kickers); higher wins, including ties across hand sizes.
EVALUATOR = '''
RANKS = "23456789TJQKA"
SUITS = "shdc"  # retain upstream deck order for the seeded preflop table
RANK_IDX = {r: i for i, r in enumerate(RANKS)}

class _Card(int):
    def __new__(cls, value):
        if isinstance(value, str):
            value = RANKS.index(value[0]) * 4 + SUITS.index(value[1])
        return int.__new__(cls, value)

    def __str__(self):
        return RANKS[self >> 2] + SUITS[self & 3]


def _straight(mask):
    consecutive = mask & (mask >> 1) & (mask >> 2) & (mask >> 3) & (mask >> 4)
    if consecutive:
        return consecutive.bit_length() + 3
    return 3 if mask & 0x100F == 0x100F else -1


def _kickers(mask, count):
    result = 0
    shift = 16
    for _ in range(count):
        rank = mask.bit_length() - 1
        result |= rank << shift
        mask ^= 1 << rank
        shift -= 4
    return result


def _evaluate(cards):
    """Independent best-five evaluator for 5-7 distinct cards; higher wins."""
    ranks = pairs = trips = quads = 0
    suits = [0, 0, 0, 0]
    for card in cards:
        bit = 1 << (card >> 2)
        quads |= trips & bit
        trips |= pairs & bit
        pairs |= ranks & bit
        ranks |= bit
        suits[card & 3] |= bit
    flush = 0
    for suited in suits:
        if suited.bit_count() >= 5:
            straight = _straight(suited)
            if straight >= 0:
                return (8 << 20) | (straight << 16)
            flush = suited
            break
    if quads:
        rank = quads.bit_length() - 1
        return (7 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 1) >> 4)
    if trips:
        rank = trips.bit_length() - 1
        other_pairs = pairs & ~(1 << rank)
        if other_pairs:
            return (6 << 20) | (rank << 16) | ((other_pairs.bit_length() - 1) << 12)
    if flush:
        return (5 << 20) | _kickers(flush, 5)
    straight = _straight(ranks)
    if straight >= 0:
        return (4 << 20) | (straight << 16)
    if trips:
        return (3 << 20) | (rank << 16) | (_kickers(ranks ^ (1 << rank), 2) >> 4)
    if pairs:
        high = pairs.bit_length() - 1
        rest = pairs ^ (1 << high)
        if rest:
            low = rest.bit_length() - 1
            remaining = ranks & ~(1 << high) & ~(1 << low)
            return (2 << 20) | (high << 16) | (low << 12) | (_kickers(remaining, 1) >> 8)
        return (1 << 20) | (high << 16) | (_kickers(ranks ^ (1 << high), 3) >> 4)
    return _kickers(ranks, 5)


class _Eval7Compatibility:
    Card = _Card
    evaluate = staticmethod(_evaluate)
    _names = ("High Card", "Pair", "Two Pair", "Trips", "Straight", "Flush",
              "Full House", "Quads", "Straight Flush")

    @staticmethod
    def handtype(score):
        return _Eval7Compatibility._names[score >> 20]


eval7 = _Eval7Compatibility()
ALL_CARDS = [eval7.Card(r + s) for r in RANKS for s in SUITS]
'''

POSITION = '''def positions(state):
    """Use the actual organizer button, preserving the source seat-distance rule."""
    n = len(state["players"])
    me, button = state["seat_to_act"], state["button"]
    sb = button if n == 2 else (button + 1) % n
    bb = (sb + 1) % n
    return n, button, sb, bb, (button - me) % n
'''

RAISE = '''def _make_raise(to_amount, state):
    """Return a legal total raise-to, including short all-in raise ranges."""
    legal = state["legal_actions"]
    low, high = state.get("min_raise_to"), state.get("max_raise_to")
    if "raise" not in legal or low is None or high is None:
        if "call" in legal:
            return {"action": "call"}
        return _safe_fallback(state)
    return {"action": "raise", "amount": int(min(high, max(low, to_amount)))}
'''

ADAPTER = '''
def _add_history(counts, history):
    for event in history:
        action = event.get("action")
        if action not in ("raise", "all_in", "call", "fold", "check"):
            continue
        seat = event.get("seat")
        if seat is None:
            continue
        key = "seat_" + str(seat)
        p = counts.setdefault(key, {"raise": 0, "call": 0, "fold": 0, "check": 0, "n": 0})
        p["raise" if action == "all_in" else action] += 1
        p["n"] += 1


def _finish_profiles(counts):
    for p in counts.values():
        p["agg"] = p["raise"] / max(1, p["n"])
        p["foldiness"] = p["fold"] / max(1, p["raise"] + p["call"] + p["fold"])
    return counts


class Agent:
    """Imperial B candidate port; no native policy improvements or performance claim."""
    def __init__(self):
        self.on_table_start({})

    def on_table_start(self, info):
        self._rng = random.Random(0xC0FFEE + int(info.get("seat", 0)))
        self._counts = {}
        self._last_completed_hand = 0

    def on_hand_end(self, summary):
        hand = int(summary.get("hand_number", 0))
        if hand <= self._last_completed_hand:
            return
        _add_history(self._counts, summary.get("history", []))
        self._last_completed_hand = hand

    def _adapt_state(self, state):
        me = state["seat"]
        stacks, bets, folded = state["stacks"], state["bets"], state["folded"]
        history = state.get("history", [])
        # Completed hands are aggregated once, outside the decision time bank.
        # Only the current hand's short history is scanned at each decision.
        profiles = {key: dict(value) for key, value in self._counts.items()}
        if state.get("hand_number", 1) > self._last_completed_hand:
            _add_history(profiles, history)
        return {
            "your_cards": state["hole_cards"], "community_cards": state["board"],
            "street": state["street"], "seat_to_act": me, "button": state["button"],
            "players": [{"seat": i, "bot_id": "seat_" + str(i),
                         "is_folded": folded[i], "stack": stacks[i]}
                        for i in range(len(stacks))],
            "your_stack": stacks[me], "your_bet_this_street": bets[me],
            "current_bet": max(bets), "amount_owed": state["to_call"],
            "pot": state["pot"], "big_blind": state["big_blind"],
            "can_check": "check" in state["legal_actions"],
            "min_raise_to": state["min_raise_to"], "max_raise_to": state["max_raise_to"],
            "legal_actions": state["legal_actions"], "action_log": history,
            "_profiles": _finish_profiles(profiles),
        }

    def act(self, state):
        legal = state.get("legal_actions", [])
        fallback = {"action": "check" if "check" in legal else "fold"}
        try:
            action = decide(self._adapt_state(state), self._rng)
            kind = action.get("action")
            if kind == "raise":
                low, high = state.get("min_raise_to"), state.get("max_raise_to")
                if "raise" in legal and low is not None and high is not None:
                    return {"action": "raise", "amount": int(min(high, max(low, action["amount"])))}
                return {"action": "call"} if "call" in legal else fallback
            return {"action": kind} if kind in legal else fallback
        except (KeyError, TypeError, ValueError, IndexError):
            return fallback
'''


def replace_function(text, name, replacement):
    tree = ast.parse(text)
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    lines = text.splitlines(keepends=True)
    return "".join(lines[:node.lineno - 1]) + replacement.rstrip() + "\n" + "".join(lines[node.end_lineno:])


def main():
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    namespace = {"random": random}
    exec(EVALUATOR, namespace)
    for name in ("_canonical_key", "_build_preflop_table"):
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
        exec(ast.get_source_segment(source, node), namespace)
    table = namespace["_build_preflop_table"]()
    assert len(table) == 169
    assert all(rank + rank in table for rank in "23456789TJQKA")

    policy = source[source.index("def _canonical_key"):]
    policy = replace_function(policy, "_build_preflop_table", "")
    policy = policy.replace("try:\n    PREFLOP_EQ = _build_preflop_table()\nexcept Exception:\n    PREFLOP_EQ = {}", "")
    policy = replace_function(policy, "positions", POSITION)
    policy = replace_function(policy, "opponent_profiles", 'def opponent_profiles(state):\n    return state["_profiles"]\n')
    policy = replace_function(policy, "_make_raise", RAISE)
    policy = policy.replace("BIG_BLIND", 'state["big_blind"]')
    policy = policy.replace("def mc_equity(hole, board, n_opp, samples, deadline):", "def mc_equity(hole, board, n_opp, samples, deadline, rng):")
    policy = policy.replace("sample = _RNG.sample", "sample = rng.sample")
    policy = policy.replace("if (i & 31) == 0 and perf_counter() > deadline:", "if perf_counter() >= deadline:")
    policy = policy.replace("samples = max(180, int(2400 / (n_opp + 1)))", "samples = MAX_MC_SAMPLES")
    policy = policy.replace('samples, ctx["deadline"])', 'samples, ctx["deadline"], ctx["rng"])')
    policy = policy.replace("_RNG.random()", 'ctx["rng"].random()')
    policy = policy.replace("def decide(game_state: dict) -> dict:", "def decide(game_state: dict, rng) -> dict:")
    policy = policy.replace('"deadline": t0 + SOFT_BUDGET,', '"deadline": t0 + SOFT_BUDGET,\n            "rng": rng,')
    # The inherited hard-budget branch never interrupted work; omit that no-op
    # rather than implying that Python can enforce a hard wall-clock ceiling.
    start = policy.index("        # Absolute safety:")
    end = policy.index("        return action\n    except Exception:", start)
    policy = policy[:start] + policy[end:]
    policy = policy.replace("# Position (derived - no button field in the state)", "# Position (official button field)")
    policy = policy.replace("# Opponent model (optional - degrades gracefully without match_action_log)", "# Opponent model (incremental official hand summaries)")
    license_text = (ROOT / "research/sources/FLOORFIX_LICENSE.txt").read_text(encoding="utf-8")
    header = '''"""Floorfix public-bot port for Imperial AI Pokerbots (B intake, not C tuning).

Upstream: txnujk09/fullhouse-poker-bot, bots/floorfix/bot.py
Revision: 4fe154318949aa60430682416f148733c6f0d564
Original policy thresholds and survival conservatism are retained. That source
assumed elimination poker; Imperial resets 100BB stacks every hand. Its survival
rationale is not an Imperial performance claim. Lower MC precision is mandatory
for the 10ms including IPC limit: at most 24 samples with a 1.5ms deadline checked
before each sample (one sample/OS scheduling may overrun it). Runtime has no files,
network, external imports or expensive preflop-table generation.

Rebuild: research/build_floorfix.py. Source and full MIT notice follow.

'''
    constants = '''
BOT_NAME = "Fullhouse Floorfix (Imperial port)"
SOFT_BUDGET = 0.0015
MAX_MC_SAMPLES = 24
T_PREMIUM = 0.66
T_STRONG = 0.585
T_PLAYABLE = 0.52
T_SPEC = 0.47
'''
    output = header + license_text + '\n"""\n\nimport random\nfrom time import perf_counter\n' + EVALUATOR + constants
    output += "\n# Original seeded 900-sample/class table; pair stream seed 67890, other seed 12345.\nPREFLOP_EQ = "
    output += pprint.pformat(table, sort_dicts=True, width=90) + "\n\n" + policy + "\n" + ADAPTER
    ast.parse(output)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(output, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}: {len(output.encode('utf-8'))} bytes, {len(table)} preflop classes")


if __name__ == "__main__":
    main()
