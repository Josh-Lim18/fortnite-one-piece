"""Template for a bot in its own process. Port this loop to any language.

Read one JSON object per line from stdin. Reply to every "act" with one JSON line on stdout.
Print logs to stderr only.
"""

import json
import sys


def decide(obs):
    # Replace this with your strategy. obs fields are documented in arena/README.md.
    if "raise" in obs["legal_actions"] and obs["hole_cards"][0][0] == obs["hole_cards"][1][0]:
        return {"action": "raise", "amount": obs["min_raise_to"]}  # min-raise pocket pairs
    return {"action": "call"}


for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "act":
        print(json.dumps(decide(message["obs"])), flush=True)
    elif message["type"] == "hand_over":
        pass  # message["result"] has payoffs, board and shown cards: use it to model opponents
    elif message["type"] == "quit":
        break
