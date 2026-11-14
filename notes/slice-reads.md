# Slice: bet-size reads and robust profiling

**Files you own:** `bot.py`, `tools/test_bot.py`, `tools/baseline_bot.py`, `opponents/switcher.py`. **Time box:** 75 minutes. Starts only after the strategy slice is merged, since both edit `bot.py`.

Owen's two ideas, made concrete.

## 1. Bet sizes give bots away

A bot written in an afternoon sizes its raises with one formula, so its exact amounts fingerprint its code. Many teams run the organisers' starter (`kit/bot.py`) nearly unchanged: Owen's own teammate's bot is the starter byte for byte. Read it: it raises to `min_raise_to + pot // 2` exactly when it holds a pocket pair or a king or ace, on every street whatever the board; it checks otherwise; facing a bet it calls up to two big blinds with anything and calls anything with a "strong" hand. Its whole strategy is therefore known once it is recognised.

- Per seat, record each raise with the state it was made in (amount, `min_raise_to`, pot, to-call) and test it against the sizing formula of each bot in `kit/examples/` and `kit/bot.py`. Count matches and misses.
- A seat that has matched one formula on at least three raises and never missed is treated as that bot. For the starter: its raise means a pair or a king or ace in hand (put that exact range into the equity estimate); its check means neither, so any bet above two big blinds wins the pot unless it is strong; value-bet big into its calls.
- For seats that match nothing, record the pot fraction of each bet and what the seat showed at showdown (`summary["shown"]`), and narrow its range for a size bucket only once it has at least five showdowns in that bucket.

## 2. Don't let a deliberate deviation fool the profile

An opponent may play out of type on purpose, or change strategy mid-round. Intent cannot be read from one move, so make the profile robust instead of guessing intent.

- Isolated moves already carry little weight because of the priors; keep that.
- Decay old observations (a half-life near 150 hands, as a param) so a seat that changes strategy is re-read within about 60 hands.
- Scale every exploit by the evidence behind it, and cap how far any single read moves a threshold, so a wrong read costs little.
- A fingerprint is dropped the first time the seat raises off-formula.
- Our own tells: on a given street our bet size must not depend on hand strength or on bluffing; add a small seeded random jitter (about ±10%, a param) to sizes so no fixed formula fingerprints us.

`opponents/switcher.py`: plays like `opponents/nit.py` for the first 300 hands of a round, then like `opponents/maniac.py`.

## Measure

Copy `bot.py` to `tools/baseline_bot.py` first. Report `tools/sim.py --vs tools/baseline_bot.py` (at least 24 rounds each, mean ± standard error) against: `kit/bot.py` only; `kit/examples/*.py` plus `kit/bot.py`; `opponents/*.py` plus `opponents/switcher.py`. The first must improve clearly; none may get worse beyond the error bars. Then `python3 kit/local_sim.py bot.py --rounds 2`: errors and thinking time.

## Test

`tools/test_bot.py` (add to what is there): a starter seat is fingerprinted within its first three raises and the fingerprint drops on an off-formula raise; against `switcher.py` the seat's entered-pot rate reads above 50% within 80 hands of the switch.
