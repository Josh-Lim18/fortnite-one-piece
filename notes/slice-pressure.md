# Slice: adaptive pressure moves

**Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`, `opponents/threshold.py`. **Time box:** 90 minutes. Starts only after the bet-size reads slice is merged, since all three bot slices edit `bot.py`. Read `bot.py` in full first and build on the counters it already keeps (per-seat rates with priors, decay, evidence caps).

## The rule (Owen)

Every assumption is adaptive. No unusual move is played by default: each one is used against a seat only when that seat's measured responses say it profits, and dropped when they stop saying so. SPEC.md, "Strategy", states it.

## Learn responses from every bet at the table

A seat's response to a bet is visible whoever made the bet, so learn from all of them, not only ours: about seven times the data, enough for a read within roughly 100 hands. Per seat, by street (flop, turn, river) and by size as a share of the pot before the bet (under 0.35, 0.35–0.8, 0.8–1.3, over 1.3), count fold, call, raise. Shrink each cell first toward the seat's overall fold-to-bet rate, then toward the table-wide rate for that cell, so sparse cells borrow strength. Also per seat: how often it bets when checked to, and how often it folds to a second and a third bet in the same hand.

## Moves, each gated by those numbers

1. **Size from the response curve.** Postflop, choose among a few candidate sizes (about 0.1, 0.33, 0.66, 1.0, 1.7 and 3 times the pot, and all in) the one with the highest expected chips against the seats still in: fold chance × pot, plus call chance × (equity against the range that continues at that size × final pot − our bet). The continuing range is the seat's range narrowed by its fold rate at that size. The same rule covers thin value with tiny bets and overbets for value or as bluffs. Keep the time to a millisecond or two: use the cheap equity estimate already in the bot, not a fresh rollout per candidate.
2. **Barrels.** With a weak hand after betting the previous street, bet again only when the seat's fold rate to a second (or third) bet makes it profitable at the chosen size.
3. **Check-raise.** Against a seat that bets often when checked to, check strong hands and some bluffs out of position intending to raise its bet.
4. **Preflop pressure.** Re-raise light against a raiser that folds to re-raises often, sized from the same response idea.

Not doing: deliberately switching our own style mid-round to fool adaptive bots. It costs value while setting up and pays only against bots that adapt, which few here do; the jitter from the reads slice keeps us hard to fingerprint.

Background, not a requirement: research on bots that round bet sizes to a fixed set found they leak chips to unusual sizes. Most bots here compute pot odds on the exact amount, so an odd number by itself breaks nothing; what earns chips is the size their own response curve says they handle badly (for example, the starter calls any bet up to two big blinds and folds weak hands to anything more).

## `opponents/threshold.py`

A bot that calls when its equity beats a fixed cutoff regardless of bet size and bets a fixed half pot: the kind an overbet exploits.

## Measure

Copy `bot.py` to `tools/baseline_bot.py` first. Report `tools/sim.py --vs tools/baseline_bot.py` (at least 24 rounds each, mean ± standard error) against: `kit/bot.py` only; `kit/examples/*.py` plus `kit/bot.py`; `opponents/*.py` including the new one. None may get worse beyond the error bars. Report how often each move fired per 1,000 hands and its chips won. Then `python3 kit/local_sim.py bot.py --rounds 2`: errors and thinking time.

## Test

`tools/test_bot.py` (add to what is there): against a seat that has folded to every overbet it faced, the bot overbets a weak hand heads-up; against a seat that has called every overbet, it does not; a seat that bets every time it is checked to gets check-raised with a strong hand.
