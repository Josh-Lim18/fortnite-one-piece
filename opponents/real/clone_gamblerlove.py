"""Clone of team gamblerlove, fitted by tools/analyze.py from 5000 hands over 5 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.012, 'open': 0.221, 'limp': 0.0, 'reraise': 0.051, 'call_raise': 0.067, 'bet': 0.544, 'raise': 0.187, 'fold_to_bet': 0.469, 'open_bb': 3.0, 'bet_pot': 0.61})
