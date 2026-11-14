"""Clone of team munchlax, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.007, 'open': 0.158, 'limp': 0.005, 'reraise': 0.036, 'call_raise': 0.215, 'bet': 0.256, 'raise': 0.014, 'fold_to_bet': 0.591, 'open_bb': 3.0, 'bet_pot': 0.55})
