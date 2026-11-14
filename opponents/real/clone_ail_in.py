"""Clone of team AIl IN, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.005, 'open': 0.205, 'limp': 0.022, 'reraise': 0.077, 'call_raise': 0.189, 'bet': 0.376, 'raise': 0.079, 'fold_to_bet': 0.265, 'open_bb': 2.5, 'bet_pot': 0.58})
