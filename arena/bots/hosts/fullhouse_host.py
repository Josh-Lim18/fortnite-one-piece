"""Host a Fullhouse Hackathon 2026 bot (a file with `decide(game_state) -> dict`) as an arena command bot.

Usage: python fullhouse_host.py path/to/bot.py

Translates the arena's JSON-lines protocol into the Fullhouse engine's game_state (format taken from the
official engine vendored in advitrocks9/fullhouse-bot: engine_vendored/engine/game.py and sandbox/match.py).
Fullhouse bots assume a 100-chip big blind, so chips are scaled by 100 / big_blind both ways.
"""

import importlib.util
import json
import os
import sys
import time

MATCH_LOG_MAX = 2000


def load_decide(path):
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    parent = os.path.dirname(folder)
    # A bot at pkg/pkg.py (advitrocks9: bot/bot.py importing bot.features) needs the parent on the path,
    # and must not have its own folder there, or "pkg" resolves to pkg.py instead of the package.
    own_name_module = os.path.exists(os.path.join(folder, os.path.basename(folder) + ".py"))
    for entry in ([parent] if own_name_module else [parent, folder]):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    spec = importlib.util.spec_from_file_location("fullhouse_bot", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["fullhouse_bot"] = module
    spec.loader.exec_module(module)
    return module.decide


def blind_seats(n):
    return (1, 0) if n == 2 else (0, 1)


def to_state(obs, match_log):
    k = 100 / obs["big_blind"]
    scale = lambda x: int(round(x * k))  # noqa: E731
    n, seat = obs["num_players"], obs["seat"]
    folded = [False] * n
    for h in obs["history"]:
        if h["action"] == "fold":
            folded[h["seat"]] = True
    sb, bb = blind_seats(n)
    log = [
        {"seat": sb, "action": "small_blind", "amount": scale(obs["small_blind"])},
        {"seat": bb, "action": "big_blind", "amount": scale(obs["big_blind"])},
    ] + [{"seat": h["seat"], "action": h["action"], "amount": scale(h["amount"])} for h in obs["history"]]
    players = []
    for s in range(n):
        all_in = obs["stacks"][s] == 0 and not folded[s]
        players.append({
            "seat": s,
            "bot_id": obs["players"][s],
            "stack": scale(obs["stacks"][s]),
            "state": "folded" if folded[s] else "all_in" if all_in else "active",
            "is_folded": folded[s],
            "is_all_in": all_in,
            "bet_this_street": scale(obs["bets"][s]),
            "hole_cards": None,
        })
    current = max(obs["bets"])
    min_to = obs["min_raise_to"] if obs["min_raise_to"] is not None else current + obs["big_blind"]
    return {
        "type": "action_request",
        "hand_id": str(obs["hand_id"]),
        "street": obs["street"],
        "seat_to_act": seat,
        "pot": scale(obs["pot"]),
        "community_cards": list(obs["board"]),
        "current_bet": scale(current),
        "min_raise_to": scale(min_to),
        "amount_owed": scale(obs["to_call"]),
        "can_check": obs["to_call"] == 0,
        "your_cards": list(obs["hole_cards"]),
        "your_stack": scale(obs["stacks"][seat]),
        "your_bet_this_street": scale(obs["bets"][seat]),
        "players": players,
        "action_log": log,
        "match_action_log": match_log[-MATCH_LOG_MAX:],
    }


def to_arena(reply, obs):
    """Apply Fullhouse's own rules: check while owing is a call, unknown actions fold."""
    k = 100 / obs["big_blind"]
    if not isinstance(reply, dict):
        return {"action": "fold"}
    action = str(reply.get("action", "fold")).lower().strip()
    if action in ("check", "call"):
        return {"action": "call"}
    if action == "all_in":
        return {"action": "raise", "amount": obs["max_raise_to"]} if obs["max_raise_to"] else {"action": "call"}
    if action == "raise":
        try:
            amount = int(reply.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0
        return {"action": "raise", "amount": int(round(amount / k))}
    return {"action": "fold"}


def main():
    proto = sys.stdout
    sys.stdout = sys.stderr  # the bot's print() must not corrupt the protocol
    decide = load_decide(sys.argv[1])
    # --limit-ms N: a decide() slower than N ms is thrown away and the bot checks or folds,
    # as the AlgoSoc platform does (10 ms per decision). Timed inside this process, so the
    # arena's pipe overhead doesn't count against the bot.
    limit_ms = float(sys.argv[sys.argv.index("--limit-ms") + 1]) if "--limit-ms" in sys.argv else None
    try:
        decide({"type": "warmup"})
    except Exception:
        pass
    match_log = []
    late = 0
    for line in sys.stdin:
        message = json.loads(line)
        if message["type"] == "act":
            obs = message["obs"]
            started = time.perf_counter()
            try:
                reply = to_arena(decide(to_state(obs, match_log)), obs)
            except Exception as e:  # the Fullhouse engine folds on a crash
                print(f"decide() raised {e!r}", file=sys.stderr)
                reply = to_arena(None, obs)
            if limit_ms is not None and (time.perf_counter() - started) * 1000 > limit_ms:
                late += 1
                print(f"late decision #{late}: over {limit_ms} ms, check/fold instead", file=sys.stderr)
                reply = {"action": "check"} if obs["to_call"] == 0 else {"action": "fold"}
            proto.write(json.dumps(reply) + "\n")
            proto.flush()
        elif message["type"] == "hand_over":
            result = message["result"]
            k = 100 / result["big_blind"]
            for h in result["history"]:
                match_log.append({
                    "hand_num": result["hand_id"] + 1,
                    "seat": h["seat"],
                    "bot_id": result["players"][h["seat"]],
                    "action": h["action"],
                    "amount": int(round(h["amount"] * k)),
                })
            del match_log[:-MATCH_LOG_MAX]
        elif message["type"] == "quit":
            break


if __name__ == "__main__":
    main()
