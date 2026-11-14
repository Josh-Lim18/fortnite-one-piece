"""Clone of team test, fitted by tools/analyze.py from 5000 hands over 5 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.0, 'open': 0.168, 'limp': 0.021, 'reraise': 0.014, 'call_raise': 0.104, 'bet': 0.299, 'raise': 0.014, 'fold_to_bet': 0.774, 'open_bb': 3.2, 'bet_pot': 0.59})
