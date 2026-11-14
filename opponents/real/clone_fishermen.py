"""Clone of team FisherMen, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.034, 'open': 0.4, 'limp': 0.012, 'reraise': 0.143, 'call_raise': 0.119, 'bet': 0.344, 'raise': 0.049, 'fold_to_bet': 0.577, 'open_bb': 3.25, 'bet_pot': 0.81})
