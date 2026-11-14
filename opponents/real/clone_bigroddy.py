"""Clone of team bigRoddy, fitted by tools/analyze.py from 6000 hands over 6 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.038, 'open': 0.215, 'limp': 0.179, 'reraise': 0.201, 'call_raise': 0.047, 'bet': 0.306, 'raise': 0.09, 'fold_to_bet': 0.488, 'open_bb': 2.5, 'bet_pot': 1.1})
