import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if message["type"] == "act":
        print("thinking...", flush=True)
        print("[1, 2]", flush=True)
        print(json.dumps({"action": "call"}), flush=True)
