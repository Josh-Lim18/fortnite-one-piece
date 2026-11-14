import json
import sys
import time

time.sleep(1.0)  # e.g. building lookup tables at import
for line in sys.stdin:
    if json.loads(line)["type"] == "act":
        print(json.dumps({"action": "call"}), flush=True)
