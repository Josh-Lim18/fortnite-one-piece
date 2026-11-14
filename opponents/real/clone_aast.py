"""Clone of team AAST, fitted by tools/analyze.py from 5000 hands over 5 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.246, 'limp': 0.001, 'reraise': 0.087, 'call_raise': 0.173, 'bet': 0.451, 'raise': 0.167, 'fold_to_bet': 0.534, 'open_bb': 3.0, 'bet_pot': 1.0})
