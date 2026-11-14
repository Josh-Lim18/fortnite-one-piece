"""Clone of team ediz_slow, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.017, 'open': 0.328, 'limp': 0.65, 'reraise': 0.244, 'call_raise': 0.184, 'bet': 0.473, 'raise': 0.171, 'fold_to_bet': 0.544, 'open_bb': 2.75, 'bet_pot': 0.57})
