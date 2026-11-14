"""Copy equity_net/weights.txt into bot.py's NET_WEIGHTS line.

    python3 equity_net/paste.py
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.join(os.path.dirname(HERE), "bot.py")
weights = open(os.path.join(HERE, "weights.txt")).read().strip()
source, n = re.subn(r'(?m)^NET_WEIGHTS = ".*"$', lambda m: 'NET_WEIGHTS = "%s"' % weights, open(BOT).read())
if n != 1:
    raise SystemExit("expected one NET_WEIGHTS line in bot.py, found %d" % n)
with open(BOT, "w") as f:
    f.write(source)
print("bot.py: NET_WEIGHTS is %d bytes" % len(weights))
