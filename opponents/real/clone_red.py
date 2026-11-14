"""Clone of team Red, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.026, 'open': 0.222, 'limp': 0.003, 'reraise': 0.037, 'call_raise': 0.125, 'bet': 0.78, 'raise': 0.128, 'fold_to_bet': 0.463, 'open_bb': 3.0, 'bet_pot': 0.5})
