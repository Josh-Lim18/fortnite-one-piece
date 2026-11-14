"""Clone of team supernut, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.005, 'open': 0.243, 'limp': 0.011, 'reraise': 0.028, 'call_raise': 0.083, 'bet': 0.433, 'raise': 0.057, 'fold_to_bet': 0.527, 'open_bb': 3.0, 'bet_pot': 1.0})
