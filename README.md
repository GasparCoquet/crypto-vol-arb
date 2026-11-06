# crypto-vol-arb

Cross-venue implied-volatility dislocations in BTC options: Deribit, OKX, Bybit, Binance.

## Question

The same BTC option (same expiry, strike, call or put) is listed on four venues.
How far apart are their implied vols, how often does one venue's bid sit above
another venue's offer, and does any of it survive fees? This is the crypto
version of multi-listed option vol arbitrage (one underlying, options listed on
US and European exchanges).

## Method (v1, one snapshot)

1. Pull the four public option chains over REST (no API key).
2. Normalise: expiry at 08:00 UTC, strike, call/put, vols as decimals. OKX,
   Bybit and Binance publish bid and ask vols. Deribit quotes inverse options in
   BTC, so its bid and ask vols are solved here with Black-76
   (`xvenue/black76.py`, Newton with a bisection fallback).
3. Deribit convention, checked rather than assumed: BTC premium × the expiry's
   forward reproduces Deribit's own mark IV to a median 0.03 vol points on 232
   liquid strikes; × the spot index misses by 0.56. So the forward is used.
4. Match options across venues; report ATM vols, each venue's gap to Deribit,
   and crossed vol markets gross and net of fees. Fees are turned into vol
   points through vega: fee_pts = 2 × fee / (vega / 100).

```
pip install -r requirements.txt
python -m pytest -q
python scan.py --save
```

## First snapshot, 2026-11-06 16:01 UTC (BTC index ≈ 75,800)

- Coverage: Deribit 938 options, OKX 1,264 (coin-margined and USD-margined),
  Bybit 686 (USDT-settled), Binance 660.
- ATM vol 37 to 40 % from November 2026 to June 2027, upward sloping. Near the
  money (strikes within 10 % of the forward) Binance marks a median 0.09 vol
  points from Deribit, OKX 0.31, Bybit 0.43, OKX USD-margined 1.11.
- Naive scan, all strikes: 904 crossed markets, 457 still positive after fees.
  Almost all are deep in-the-money options, where the premium is nearly all
  intrinsic, vega is close to zero and a vol is ill-conditioned. Not signal.
- Out-of-the-money options within 25 % log-moneyness: 461 crossed, 167 after
  fees. The largest (≈ 2.4 vol points, March 2027) all involve OKX
  USD-margined, whose March 2027 forward is 76,428 against ≈ 77,400 on the
  other venues, 1.2 % lower. A lower forward lifts call vols and lowers put
  vols for the same USD price, which is exactly the pattern: its calls look
  rich, its puts cheap. **So v1 does not show tradeable arbitrage yet; it shows
  that comparing published vols across venues mixes in their forward
  conventions.**

## Assumptions and limits

- Fees: one taker fee per leg for every venue, 0.03 % of the underlying capped
  at 12.5 % of the premium. Each venue's real schedule replaces this in v2.
- Top of book only; Deribit and Binance sizes are not read yet.
- Venues are fetched one after the other, about a second apart.
- Inverse (Deribit, OKX coin-margined) and linear (USDT) payoffs are compared
  on vols only; the BTC-settled payoff changes the hedge, not the vol.

## Next

1. Recompute every vol from USD prices on one forward per expiry, then recount
   the crossings. This separates real dislocations from conventions.
2. Read sizes and depth: how much could actually be traded.
3. Snapshot every 5 minutes for a week: how often, how large, how long
   (half-life) a dislocation lasts.
4. Fit SVI per venue and expiry; compare level, skew and curvature, the
   factors a vol book is hedged and attributed on; check butterfly and
   calendar arbitrage on each venue.
5. Delta hedge with perpetuals and pay funding; simulate the vol-arb P&L with
   fees, slippage and latency.
