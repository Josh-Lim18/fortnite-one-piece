"""Clone of team Claudebot, fitted by tools/analyze.py from 3000 hands over 3 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.015, 'open': 0.289, 'limp': 0.007, 'reraise': 0.03, 'call_raise': 0.097, 'bet': 0.287, 'raise': 0.051, 'fold_to_bet': 0.437, 'open_bb': 3.0, 'bet_pot': 0.62})
