"""Clone of team YSL_TWIZZY, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.44, 'limp': 0.009, 'reraise': 0.038, 'call_raise': 0.123, 'bet': 0.272, 'raise': 0.042, 'fold_to_bet': 0.293, 'open_bb': 2.6, 'bet_pot': 0.48})
