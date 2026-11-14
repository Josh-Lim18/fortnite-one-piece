"""Clone of team WBot, fitted by tools/analyze.py from 4000 hands over 4 rounds."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clone_base import make_agent  # noqa: E402

Agent = make_agent({'shove': 0.003, 'open': 0.423, 'limp': 0.001, 'reraise': 0.059, 'call_raise': 0.273, 'bet': 0.913, 'raise': 0.305, 'fold_to_bet': 0.43, 'open_bb': 3.5, 'bet_pot': 0.33})
