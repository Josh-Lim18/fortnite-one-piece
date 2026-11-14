"""Clone of team SmartBGerBot, fitted by tools/analyze.py from 2000 hands over 2 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.0, 'open': 0.22, 'limp': 0.001, 'reraise': 0.023, 'call_raise': 0.058, 'bet': 0.38, 'raise': 0.061, 'fold_to_bet': 0.407, 'open_bb': 3.0, 'bet_pot': 0.62})
