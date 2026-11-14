"""Clone of team Mohil'sPokerBot, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.009, 'open': 0.242, 'limp': 0.017, 'reraise': 0.094, 'call_raise': 0.116, 'bet': 0.668, 'raise': 0.106, 'fold_to_bet': 0.458, 'open_bb': 2.5, 'bet_pot': 0.5})
