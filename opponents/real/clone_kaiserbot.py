"""Clone of team kaiserbot, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.004, 'open': 0.179, 'limp': 0.018, 'reraise': 0.051, 'call_raise': 0.218, 'bet': 0.35, 'raise': 0.052, 'fold_to_bet': 0.466, 'open_bb': 2.5, 'bet_pot': 0.66})
