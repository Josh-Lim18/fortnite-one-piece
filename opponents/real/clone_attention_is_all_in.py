"""Clone of team Attention Is All In, fitted by tools/analyze.py from 2000 hands over 2 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.004, 'open': 0.234, 'limp': 0.01, 'reraise': 0.093, 'call_raise': 0.178, 'bet': 0.575, 'raise': 0.11, 'fold_to_bet': 0.51, 'open_bb': 2.5, 'bet_pot': 0.65})
