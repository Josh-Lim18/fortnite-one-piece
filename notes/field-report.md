# Field report: the real teams

Sat 14 Nov, 17:20 GMT, from `hands/` (40 rounds: 16 practice, counted rounds r001–r024; each 1,000 hands at a 6–8 seat table, so about 260 seat-rounds). Made with:

```
python3 tools/analyze.py 'hands/saturday_r*.json' --teams     # counted rounds: the table below
python3 tools/analyze.py hands/ --teams                       # practice as well
```

Error bars: a rate over 4,000 hands is good to about ±1.5 points; a rate "of 50" decisions to ±14. bb/100 is chips against the whole table the team sat at, ± one standard error over hands; tables differ, so it ranks teams only roughly.

## Top findings

1. **The counted field is tight-aggressive, not a field of starters.** 40 rival teams; in counted rounds the median team plays 23% of hands and raises 16%. Only **ediz_slow** still runs the starter (100% of its raises are exactly `min_raise_to + pot // 2`; −279 ± 55 bb/100). In practice five more used it about half the time (Attention Is All In 60%, Phil AIvey 56%, bigRoddy 47%, FisherMen 45%, Lehman Brothers 41%); all five have replaced it.
2. **No calling stations.** Every team folds at least 12% to small bets and 33%+ to pot-sized ones. Gains measured against `calling_station.py` or the starter overstate us.
3. **Big bets get folds, small bets get called.** Every rival facing a postflop bet, counted rounds:

   | bet faced (share of the pot before it) | faced | folded | a pure bluff breaks even at |
   |---|---|---|---|
   | up to 0.4 | 3,533 | 27% | about 25% |
   | 0.4–0.8 | 8,630 | 49% | about 38% |
   | 0.8–1.25 | 2,782 | 63% | about 50% |
   | over 1.25 | 390 | 78% | about 58% |
   | a call of 800+ chips | 1,780 | 52% | |

   The margin over break-even grows with size: bluffs and semi-bluffs should be pot-sized or bigger; thin value bets should be small.
4. **We lost by being a nit.** Joca's counted rounds 1–20 (v2) played 10% of hands and raised 3%: −32 ± 6 bb/100, the worst steady loss in the field after ediz_slow. Every team under 16% VPIP loses or breaks even (test −23, SmartBGerBot −12, Peanut Cookies −8).
5. **Two teams bluff with small bets.** WBot (71% postflop aggression, 0.33-pot bets, 132 weak hands to 64 strong at showdown after raising) and Chinese people can fly (0.33-pot bets, 72 weak to 51 strong): call and raise their small bets lighter.

## Groupings (counted rounds)

| Kind | Teams | Why |
|---|---|---|
| Starter | ediz_slow | 100% starter bet size, 79% VPIP, 11% limps |
| Calling station | none; loosest callers YSL_TWIZZY, AIl IN, Astra La Vista, ND | fold only 12–16% to small bets and 30–45% to medium ones, 18–26% postflop aggression |
| Maniac | WBot, Red, Anton | 71% / 60% postflop aggression; Anton 3-bets 31% |
| Nit | test, Peanut Cookies, SmartBGerBot (and Joca v2) | VPIP 10–15%; test folds 67–100% to every bet size |
| Strong | Attention Is All In (+97 ± 30), Gherkers (+85 ± 24), Anker Batteries (+74 ± 25), Equity Engine (+49 ± 23), kaiserbot (+46 ± 22), AAST (+44 ± 20) | positive over 4+ rounds (Attention 2); also Gherkers +130 ± 26 and Chinese people can fly +117 ± 21 over all 10 rounds |

## What separates winners from losers

Winners (13 teams at +30 bb/100 or more) against losers (10 teams at −10 or less), counted rounds:

| | VPIP | PFR | 3-bet | shove | limp | postflop aggression | fold to a bet |
|---|---|---|---|---|---|---|---|
| winners | 24.8% | 17.5% | 8.9% | 0.6% | 0.9% | 36% | 48% |
| losers | 31.4% | 21.1% | 13.8% | 1.3% | 11.4% | 31% | 50% |

- Raise or fold preflop; never limp (winners limp 1% of unraised pots, losers 11%).
- Play about a quarter of hands: under 16% loses the blinds, over 33% loses at showdown.
- Re-raise selectively (about 9%) and almost never open-shove (under 1%); the 3–4% shovers (bigRoddy, Red, FisherMen) lose.
- Bet more postflop (36% against 31%), and size bluffs big: the field folds 63–78% to pot-sized and bigger bets.

## Clones

`opponents/real/clone_<team>.py`: one per rival team with 2,000+ counted-round decisions (38 teams), from `tools/analyze.py 'hands/saturday_r*.json' --emit opponents/real/`, playing `opponents/clone_base.py` from the team's rates. Seated at clone-only tables (56 tables, all-round fit), clones matched their team within a mean 2.4 points of VPIP, 1.4 of PFR, 2.1 of 3-bet, 4.2 of fold to a bet, but 6.3 of postflop betting when checked to (worst 31) and they shove 1–6 points too often (re-raise wars between clones reach 800 chips). Postflop play is the roughest part: clones use fixed hand-strength bands, not each team's.

## Per team, counted rounds

Fold to bet is by the size faced as a share of the pot before it; "starter size" is the share of raises below all-in that equal `min_raise_to + pot // 2`; showdowns count the team's made hand on the river (weak: no pair or a pair below top pair; strong: top pair or better) by its last action.

| team | rounds | hands | decisions | bb/100 ± se | vpip | pfr | 3-bet | shove | postflop aggr | fold to bet <=0.4 / <=0.8 / <=1.25 / over / 800+ pot | open bb | bet pot | starter size | showdowns after raising: weak / strong | showdowns after calling: weak / strong |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Attention Is All In | 2 | 2000 | 2765 | +97 ± 30 | 26% | 16% | 9% | 0% | 42% | 23% / 49% / 70% / 92% / 62% | 2.5 | 0.65 | 0% | 16 / 22 | 6 / 9 |
| Gherkers | 4 | 4000 | 5761 | +85 ± 24 | 35% | 26% | 19% | 0% | 42% | 37% / 45% / 81% / 100% / 55% | 3.5 | 0.70 | 1% | 18 / 44 | 14 / 32 |
| Anker Batteries | 4 | 4000 | 5247 | +74 ± 25 | 24% | 18% | 13% | 1% | 44% | 40% / 54% / 65% / 83% / 37% | 2.5 | 1.10 | 1% | 31 / 37 | 6 / 30 |
| Equity Engine | 4 | 4000 | 5333 | +49 ± 23 | 25% | 20% | 3% | 0% | 38% | 31% / 55% / 57% / 90% / 59% | 3.5 | 0.80 | 0% | 10 / 27 | 27 / 24 |
| kaiserbot | 4 | 4000 | 5550 | +46 ± 22 | 22% | 12% | 5% | 0% | 26% | 26% / 49% / 59% / 40% / 63% | 2.5 | 0.66 | 1% | 11 / 28 | 25 / 31 |
| AAST | 5 | 5000 | 6528 | +44 ± 20 | 24% | 16% | 9% | 0% | 33% | 28% / 56% / 65% / 100% / 62% | 3.0 | 1.00 | 0% | 12 / 35 | 19 / 38 |
| Jump Street | 1 | 1000 | 1251 | +43 ± 35 | 18% | 12% | 5% | 0% | 28% | 29% / 58% / 75% / - / 67% | 3.0 | 0.62 | 0% | 0 / 6 | 0 / 6 |
| Kojack | 3 | 3000 | 3734 | +41 ± 31 | 19% | 16% | 11% | 1% | 27% | 25% / 56% / 61% / 100% / 52% | 2.5 | 0.55 | 0% | 9 / 33 | 26 / 14 |
| Mohil'sPokerBot | 4 | 4000 | 5208 | +38 ± 23 | 22% | 17% | 9% | 1% | 47% | 31% / 44% / 64% / 100% / 57% | 2.5 | 0.50 | 0% | 22 / 34 | 10 / 22 |
| GamesGone | 4 | 4000 | 6006 | +37 ± 29 | 31% | 20% | 4% | 1% | 49% | 18% / 42% / 53% / 74% / 51% | 2.2 | 0.59 | 0% | 34 / 45 | 52 / 38 |
| pokermon | 1 | 1000 | 1285 | +33 ± 30 | 26% | 20% | 6% | 0% | 25% | 56% / 79% / 100% / 100% / 33% | 3.0 | 0.50 | 0% | 2 / 7 | 1 / 2 |
| ND | 3 | 3000 | 4089 | +32 ± 31 | 21% | 12% | 8% | 1% | 25% | 13% / 45% / 49% / 83% / 41% | 3.0 | 0.75 | 1% | 11 / 38 | 35 / 23 |
| Phil AIvey | 4 | 4000 | 5225 | +30 ± 18 | 23% | 18% | 6% | 1% | 23% | 23% / 50% / 56% / 86% / 72% | 3.0 | 0.55 | 0% | 9 / 33 | 23 / 22 |
| Resonance Qt | 6 | 6000 | 7880 | +26 ± 17 | 24% | 18% | 11% | 1% | 33% | 22% / 46% / 61% / 70% / 64% | 3.0 | 0.80 | 0% | 33 / 35 | 33 / 30 |
| supernut | 4 | 4000 | 4914 | +23 ± 15 | 19% | 15% | 3% | 0% | 30% | 39% / 57% / 55% / 20% / 54% | 3.0 | 1.00 | 1% | 9 / 20 | 6 / 17 |
| munchlax | 4 | 4000 | 5446 | +19 ± 20 | 19% | 10% | 4% | 1% | 17% | 54% / 54% / 88% / 96% / 35% | 3.0 | 0.55 | 0% | 13 / 38 | 20 / 18 |
| Vlad | 3 | 3000 | 3965 | +18 ± 29 | 22% | 16% | 4% | 0% | 38% | 18% / 46% / 45% / 60% / 35% | 3.5 | 0.80 | 0% | 16 / 31 | 24 / 17 |
| matcha mille crêpes cake | 4 | 4000 | 5402 | +16 ± 23 | 21% | 13% | 8% | 1% | 33% | 15% / 43% / 61% / 50% / 48% | 2.5 | 0.60 | 0% | 15 / 46 | 31 / 32 |
| WBot | 4 | 4000 | 6002 | +14 ± 29 | 38% | 27% | 6% | 0% | 71% | 23% / 40% / 53% / 100% / 53% | 3.5 | 0.33 | 0% | 132 / 64 | 15 / 34 |
| Durahim 1453 | 4 | 4000 | 5177 | +13 ± 21 | 24% | 20% | 9% | 1% | 38% | 37% / 56% / 66% / 77% / 42% | 2.5 | 0.66 | 0% | 24 / 31 | 10 / 25 |
| Chinese people can fly | 4 | 4000 | 6269 | +12 ± 22 | 37% | 26% | 5% | 1% | 48% | 38% / 54% / 60% / 79% / 43% | 2.5 | 0.33 | 0% | 72 / 51 | 13 / 33 |
| gamblerlove | 5 | 5000 | 5975 | +11 ± 14 | 17% | 13% | 5% | 1% | 40% | 21% / 45% / 67% / 91% / 60% | 3.0 | 0.61 | 1% | 19 / 23 | 10 / 9 |
| Astra La Vista | 4 | 4000 | 5121 | +9 ± 22 | 20% | 15% | 7% | 1% | 48% | 13% / 45% / 46% / 50% / 54% | 3.0 | 0.50 | 0% | 28 / 37 | 27 / 20 |
| AIl IN | 3 | 3000 | 4243 | +1 ± 30 | 24% | 15% | 8% | 0% | 26% | 12% / 30% / 33% / 0% / 27% | 2.5 | 0.58 | 0% | 7 / 22 | 54 / 36 |
| Poke | 3 | 3000 | 4199 | +1 ± 21 | 27% | 15% | 4% | 0% | 34% | 24% / 57% / 62% / 75% / 52% | 3.0 | 0.75 | 0% | 13 / 23 | 10 / 22 |
| FisherMen | 4 | 4000 | 5694 | -2 ± 28 | 34% | 28% | 14% | 3% | 23% | 30% / 65% / 68% / 67% / 59% | 3.2 | 0.81 | 1% | 52 / 41 | 10 / 32 |
| aydine | 3 | 3000 | 4024 | -2 ± 28 | 22% | 15% | 4% | 0% | 38% | 16% / 42% / 61% / - / 41% | 3.5 | 0.80 | 0% | 14 / 20 | 31 / 21 |
| Claudebot | 3 | 3000 | 3778 | -4 ± 23 | 21% | 17% | 3% | 2% | 20% | 27% / 45% / 70% / 67% / 52% | 3.0 | 0.62 | 0% | 7 / 16 | 20 / 19 |
| Peanut Cookies | 2 | 2000 | 2325 | -8 ± 15 | 14% | 13% | 5% | 0% | 19% | 14% / 38% / 67% / 25% / 33% | 2.5 | 0.70 | 0% | 1 / 4 | 5 / 8 |
| The Market Makers | 3 | 3000 | 4067 | -9 ± 27 | 21% | 15% | 8% | 1% | 35% | 22% / 50% / 64% / 100% / 67% | 2.5 | 0.70 | 1% | 19 / 26 | 21 / 22 |
| Anton | 5 | 5000 | 7474 | -11 ± 33 | 38% | 31% | 31% | 1% | 23% | 29% / 43% / 60% / 100% / 44% | 3.8 | 0.60 | 0% | 24 / 50 | 133 / 91 |
| SmartBGerBot | 2 | 2000 | 2376 | -12 ± 15 | 15% | 12% | 2% | 0% | 24% | 27% / 53% / 24% / 100% / 56% | 3.0 | 0.62 | 0% | 2 / 1 | 8 / 8 |
| Red | 4 | 4000 | 4889 | -13 ± 23 | 19% | 14% | 4% | 3% | 60% | 42% / 46% / 64% / 100% / 34% | 3.0 | 0.50 | 0% | 37 / 45 | 21 / 10 |
| bigRoddy | 6 | 6000 | 8363 | -19 ± 23 | 29% | 21% | 20% | 4% | 23% | 34% / 50% / 58% / 50% / 58% | 2.5 | 1.10 | 0% | 71 / 68 | 44 / 31 |
| Poké Bot | 4 | 4000 | 5512 | -22 ± 22 | 26% | 20% | 4% | 0% | 33% | 24% / 44% / 59% / 92% / 68% | 3.0 | 0.75 | 0% | 13 / 31 | 26 / 33 |
| test | 5 | 5000 | 5994 | -23 ± 7 | 15% | 9% | 1% | 0% | 18% | 67% / 79% / 84% / 100% / 81% | 3.2 | 0.59 | 0% | 1 / 8 | 3 / 11 |
| Joca (us) | 24 | 24000 | 29056 | -32 ± 6 | 10% | 3% | 2% | 0% | 21% | 38% / 45% / 45% / 60% / 39% | 3.0 | 0.50 | 0% | 57 / 83 | 106 / 50 |
| SARS | 5 | 5000 | 6469 | -39 ± 16 | 27% | 20% | 18% | 0% | 38% | 30% / 63% / 76% / 75% / 63% | 2.5 | 0.60 | 0% | 18 / 16 | 16 / 26 |
| YSL_TWIZZY | 3 | 3000 | 4650 | -47 ± 25 | 33% | 27% | 4% | 0% | 18% | 13% / 33% / 42% / 43% / 32% | 2.6 | 0.48 | 0% | 4 / 18 | 41 / 32 |
| Lehman Brothers | 2 | 2000 | 2958 | -49 ± 35 | 29% | 23% | 5% | 1% | 42% | 35% / 49% / 59% / 65% / 66% | 2.6 | 0.60 | 1% | 24 / 18 | 12 / 13 |
| ediz_slow | 4 | 4000 | 8897 | -279 ± 55 | 79% | 32% | 24% | 2% | 36% | 32% / 51% / 81% / 92% / 49% | 2.8 | 0.57 | 100% | 80 / 62 | 227 / 150 |
