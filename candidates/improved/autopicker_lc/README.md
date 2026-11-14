# autopicker-lc (lane C research bot)

> **Research candidate, not an upload candidate.** The live bot is v1-fast (`bot.py` on `poker/live`). In the team simulator
> (`tools/sim.py`, paired seeds, default pool) autopicker-lc loses to v1-fast by **-37.6 ± 10.0 bb/100** (160 rounds).
> What it does show: its layers 2-4 beat its own layer 1 by **+16.5 ± 5.5 bb/100**, so the auto-picker idea is worth porting.

One standalone AlgoSoc-kit bot (`bot.py`: `Agent()`, `on_table_start`, `act`, `on_hand_end`) built in four layers.
`bot.py` is **generated**: edit `layers_v1.py` or the plug-ins, then run `python3 build.py`.

```
1. Baseline knowledge      tournament plug-ins (preflop table, shove defence, multiway betting)
                           + v1 rules: heads-up betting, facing-bet pricing vs a range, pot-fraction sizing
2. Opponent profiles       one shared stat profile per seat: vpip, pfr, shove, postflop aggression, fold-to-bet
                           (long-run with slow decay + recent window of 30) + showdown strength of shown hands
3. Personalities           8 labels + unknown, derived from the profile (shover, maniac, station, nit, tight_passive,
                           loose_passive, folder, balanced), each mapped to response settings ("knobs");
                           blended toward by confidence = hands / (hands + 30); label must persist 3 updates to change
4. Auto picker + safety    surprise score (largest z of recent vs long-run rate) drives 4 states per opponent:
                             in_character -> personality knobs
                             deviating    -> out-of-character pool, chosen by the direction of the deviation
                                             (aggression up: respect, then call down once junk is shown;
                                              tightening; loosening; robust)
                             changed      -> deviation persisted 40 hands: relearn from the recent window
                             reactive     -> aggression aimed at us vs the field (z > 3): small exploits only
                           safety nets: per-opponent stop-loss (-150 bb over 40 attributed hands -> exploits off
                           for 60 hands), bluff share estimated from showdowns (mixture model), action sanitizer,
                           try/except fallback to check/fold, 0.3 ms equity budget and a 5 ms time guard (platform limit 10 ms)
```

Knobs per opponent: `jam_width` (assumed all-in range width), `bet_f` (width multiplier for their betting range),
`bluff_r` (share of random hands in their aggression), `value_mult` (our value sizing vs them), `bluff_ok`.

## Rebuild / variants
```
python3 build.py                                   # bot.py and bot_baseline.py (layers 2-4 off)
python3 build.py --set _V1_USE_PICKER=False --out /tmp/nopicker.py     # personalities, no deviation states
python3 build.py --shove minimal                   # swap in the backup shove-defence plug-in
```

## Test in Josh's arena (authoritative, uses PokerKit)
Registered in `arena/bots.toml` as `autopicker-lc`, `autopicker-lc-baseline` and `incumbent-vivelev`; the entries point at
the files in `candidates/` (one copy each).
```
cd arena
uv run arena table autopicker-lc autopicker-lc-baseline incumbent-vivelev call allin random --stack 2000 --sb 10 --bb 20 --until-decided --deals 50 --max-deals 3000
```
Against v1-fast use the team simulator on `poker/live`: `python3 tools/sim.py <path>/bot.py --vs bot.py --rounds 160 --seed 7`.

## Results
Team simulator on `poker/live` (`tools/sim.py`, official kit engine, paired seeds, default pool of `kit/examples` + `opponents`):

| paired match (160 rounds, seed 7) | bb/100 ± stderr |
|---|---|
| autopicker-lc vs v1-fast | -37.6 ± 10.0 |
| autopicker-lc-baseline vs v1-fast | -58.9 ± 11.1 |
| autopicker-lc vs autopicker-lc-baseline (layers 2-4 on vs off) | **+16.5 ± 5.5** |

Thinking time, 8-seat tables of the default pool, 3 rounds of 1,000 hands: autopicker-lc 0.136 ms/decision (max 2.8 ms),
0.16-0.24 s per round; v1-fast 0.148 ms/decision (max 2.3 ms), 0.17-0.23 s per round. Budgets: equity 0.3 ms, multiway
plug-in 0.4 ms, shove plug-in 0.6 ms, fallback 0.3 ms.

Earlier numbers vs the VIVelev incumbent (+81 to +833 bb/100) came from a dependency-free arena used during the tournament,
which is not included here; see `tournament/RESULTS.md`.
