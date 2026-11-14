import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bot import Agent, analyse_mechanics, legalise_action, pot_layers

KIT = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir() else Path(os.environ.get('KIT', HERE.parents[1] / 'kit'))
sys.path.insert(0, str(KIT))
from engine.game import FixedHandsTable
from engine.players import LocalPlayer, SubprocessPlayer


def state():
    return dict(hand_number=1, street='preflop', seat=0, button=5,
                hole_cards=['As', 'Kd'], board=[], stacks=[2000, 1990, 1980, 2000, 2000, 2000, 2000],
                bets=[0, 10, 20, 0, 0, 0, 0], folded=[False]*7,
                pot=30, to_call=20, min_raise_to=40, max_raise_to=2000,
                legal_actions=['fold', 'call', 'raise'], history=[],
                betting='no_limit', raise_cap=None, raises_this_street=0)


class MechanicsTests(unittest.TestCase):
    def test_call_odds(self):
        a = analyse_mechanics(state(), [2000]*7)
        self.assertEqual(a['call_equity_threshold'], .4)
        self.assertEqual(a['eligible_pot_after_call'], 50)

    def test_side_pots_and_dead_money(self):
        layers = pot_layers([100, 300, 300, 50], [False, False, False, True])
        self.assertEqual([p['amount'] for p in layers], [200, 150, 400])
        self.assertEqual(layers[0]['eligible'], [0, 1, 2])
        s = state()
        s.update(stacks=[0, 0, 0, 0], bets=[100, 300, 300, 50], folded=[False, False, False, True],
                 pot=750, to_call=0, seat=0, button=3)
        a = analyse_mechanics(s, [100, 300, 300, 50])
        self.assertEqual(a['eligible_pot_after_call'], 350)

    def test_short_call_excludes_ineligible_pot(self):
        s = state()
        s.update(stacks=[20, 0, 100], bets=[0, 100, 100], folded=[False]*3,
                 pot=200, to_call=20, button=2)
        a = analyse_mechanics(s, [20, 100, 200])
        self.assertEqual(a['eligible_pot_after_call'], 60)
        self.assertAlmostEqual(a['call_equity_threshold'], 1/3)

    def test_uncalled_excess(self):
        self.assertTrue(pot_layers([100, 20], [False, False])[-1]['uncalled'])

    def test_missing_contributions_not_guessed(self):
        self.assertIsNone(analyse_mechanics(state())['pot_layers'])
        self.assertIsNone(analyse_mechanics(state(), [999]*7)['call_equity_threshold'])

    def test_raise_bounds_and_fallbacks(self):
        s = state()
        for amount, expected in [(-1, 40), (9999, 2000), (100, 100), (float('nan'), 40), (True, 40)]:
            self.assertEqual(legalise_action(s, {'action': 'raise', 'amount': amount})['amount'], expected)
        s.update(legal_actions=['fold', 'call'], min_raise_to=None, max_raise_to=None)
        self.assertEqual(legalise_action(s, {'action': 'raise', 'amount': 200}), {'action': 'fold'})
        s.update(legal_actions=['check'], to_call=0)
        self.assertEqual(legalise_action(s, None), {'action': 'check'})

    def test_short_raise_and_fixed_limit(self):
        s = state()
        s.update(min_raise_to=30, max_raise_to=30)
        self.assertEqual(legalise_action(s, {'action': 'raise', 'amount': 200})['amount'], 30)
        s.update(betting='fixed_limit', min_raise_to=40, max_raise_to=40)
        self.assertEqual(legalise_action(s, {'action': 'raise', 'amount': 200})['amount'], 40)

    def test_position(self):
        for n in (7, 8):
            for button in range(n):
                s = state()
                s.update(button=button, stacks=[2000]*n, bets=[0]*n, folded=[False]*n, pot=0)
                a = analyse_mechanics(s)
                self.assertEqual(a['postflop_positional_order'][-1], button)
                s['folded'][button] = True
                self.assertNotIn(button, analyse_mechanics(s)['postflop_positional_order'])

    def test_lifecycle_and_no_mutation(self):
        a = Agent(1)
        info = dict(seat=0, starting_stack=2000, num_players=7, stacks_reset_each_hand=True)
        a.on_table_start(info)
        s = state()
        s['history'] = [dict(seat=2, street='preflop', action='big_blind', amount=20)]
        old = copy.deepcopy(s)
        a.act(s); a.act(s)
        self.assertEqual(len(a.analysis['history']), 1)
        self.assertEqual(s, old)
        summary = dict(hand_number=1, stacks=[2030]*7, winners=[])
        a.on_hand_end(summary); a.on_hand_end(summary)
        self.assertEqual(a.round_stats['hands'], 1)
        self.assertEqual(a.round_stats['net_chips'], 30)
        s.update(hand_number=2, history=[])
        a.act(s)
        self.assertEqual(a.analysis['history'], [])
        a.on_table_start(info)
        self.assertEqual(a.round_stats['hands'], 0)


class CheckedAgent(Agent):
    streets = set()
    calls_all_in = 0
    def act(self, s):
        out = super().act(s)
        assert out['action'] in s['legal_actions']
        if out['action'] == 'raise':
            assert type(out['amount']) is int
            assert s['min_raise_to'] <= out['amount'] <= s['max_raise_to']
        a = self.analysis
        assert a['contributions'] is not None
        assert sum(p['amount'] for p in a['pot_layers']) == s['pot']
        assert sum(p['amount'] for p in a['pot_layers_after_call']) == s['pot'] + s['to_call']
        self.streets.add(s['street'])
        type(self).calls_all_in += int(a['call_is_all_in'])
        return out


def integration():
    results = []
    for n in (7, 8):
        for betting, cap in [('no_limit', 0), ('no_limit', 2), ('pot_limit', 0), ('fixed_limit', 0)]:
            players = [LocalPlayer(CheckedAgent) for _ in range(n)]
            result = FixedHandsTable(players, hands=150, config={'betting': betting, 'raise_cap': cap}, seed=42).play()
            assert sum(result['chips']) == 0
            assert all(p.stats.errors == 0 for p in players), [p.stats.as_dict() for p in players]
            assert all(p.agent.round_stats['hands'] == 150 for p in players)
            assert all(p.agent.round_stats['net_chips'] == result['chips'][i] for i, p in enumerate(players))
            results.append(dict(players=n, betting=betting, cap=cap,
                                decisions=sum(p.stats.decisions for p in players),
                                max_ms=max(p.stats.max_ms for p in players), errors=0))
    assert CheckedAgent.streets == {'preflop', 'flop', 'turn', 'river'}
    assert CheckedAgent.calls_all_in > 0
    # Official subprocess runner, default 10 ms and 10-second round bank.
    strict = []
    for n in (7, 8):
        target = SubprocessPlayer(str(HERE / 'bot.py'), timeout_ms=10, bank_ms=10000)
        players = [target] + [LocalPlayer(Agent) for _ in range(n-1)]
        try:
            result = FixedHandsTable(players, hands=1000, seed=94+n).play()
            assert sum(result['chips']) == 0
            strict.append(dict(players=n, hands=1000, **target.stats.as_dict(), total_ms=target.stats.total_ms))
        finally:
            target.close()
    report = dict(python=sys.version, size_bytes=(HERE/'bot.py').stat().st_size,
                  in_process=results, subprocess=strict,
                  streets=sorted(CheckedAgent.streets), short_calls=CheckedAgent.calls_all_in)
    (HERE/'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(MechanicsTests))
    if not result.wasSuccessful():
        sys.exit(1)
    integration()
