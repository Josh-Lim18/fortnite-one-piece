"""Clone of team ND, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.007, 'open': 0.16, 'limp': 0.039, 'reraise': 0.084, 'call_raise': 0.187, 'bet': 0.345, 'raise': 0.103, 'fold_to_bet': 0.391, 'open_bb': 3.0, 'bet_pot': 0.75})
