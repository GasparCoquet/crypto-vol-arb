# crypto-vol-arb

Cross-venue implied-volatility dislocations in BTC options: Deribit, OKX, Bybit, Binance.

## Question

The same BTC option (same expiry, strike, call or put) is listed on four venues.
How far apart are their implied vols, how often does one venue's bid sit above
another venue's offer, and does any of it survive fees? This is the crypto
version of multi-listed option vol arbitrage (one underlying, options listed on
US and European exchanges).

## Method v1: the vols each venue publishes (scan sections 0-3)

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

## Method v2: prices on one forward (scan sections 4-7)

v1 compared the vols each venue publishes, and each venue computes them on its
own forward. v2 recomputes every vol from prices (`xvenue/common.py`):

1. Every premium in USD today: linear options (USD, USDT, USDC) as quoted,
   inverse options (premium in BTC) times the spot index.
2. Each venue's forward backed out of its own call and put mids by put-call
   parity. With a zero BTC rate and a USD discount factor S / F, inverse and
   linear books give the same relation: (C - P) / S = 1 - K / F.
3. One forward per expiry: the median of the venues' parity forwards.
4. Every bid, ask and mid turned back into a Black-76 vol on that forward, so
   two vols differ only if two prices differ. Crossed markets are counted on
   USD prices, which no forward convention can create or remove.
5. SVI fitted per venue and expiry on out-of-the-money mid vols, weighted by
   1 / bid-ask width (`xvenue/svi.py`), read back as level (ATM vol), skew
   (vol points per +10% log-moneyness) and curvature, with Gatheral's
   butterfly condition and a calendar check (total variance rising with T).

## First snapshot (v1), 2026-11-06 16:01 UTC (BTC index ≈ 75,800)

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

## Second snapshot (v2), 2026-11-09 16:38 UTC (BTC index ≈ 74,940)

Run from a cloud machine where Bybit (403) and Binance (451) block the request,
so Deribit and OKX only (coin-margined and USD-margined). Rerun from Europe for
all four.

- **The v1 gap was the forward convention, confirmed.** OKX USD-margined
  publishes forwards up to 129 bps below the common forward (March 2027), but
  the forward its own prices imply by put-call parity is within 7 bps.
- Near the money, OKX USD-margined's median absolute gap to Deribit falls from
  1.42 vol points on published vols to 0.33 on the common forward (OKX
  coin-margined: 0.25 to 0.22).
- Crossed markets, out of the money within 25% log-moneyness: 155 gross and 67
  net of fees on published vols; on USD prices, 15 gross and **0 net of fees**.
- All strikes on USD prices: 22 survive fees, all in the money, all March 2027,
  OKX USD-margined against Deribit. In the money the premium is mostly forward,
  so a few bps of difference in the forward or discount rate between a linear
  and an inverse book outweighs the fee. That is a carry difference to price
  with funding and margin, not a vol dislocation.
- SVI: OKX and OKX USD-margined sit within about 0.1 vol point of Deribit on
  level, skew and curvature (median over shared expiries). No butterfly or
  calendar break on any venue. Deribit's ATM vol rises from 37.7 % (November
  2026) to 40.5 % (September 2027); skew goes from -3.2 to -0.6 vol points per
  +10% log-moneyness.

**Reading: on prices and one forward, the venues agree to within fees at this
snapshot. Any vol-arb edge has to come from moments, not from the average
snapshot, which is what the time series (next step) measures.**

## Assumptions and limits

- Fees: one taker fee per leg for every venue, 0.03 % of the underlying capped
  at 12.5 % of the premium. Each venue's real schedule replaces this in v2.
- Top of book only; Deribit and Binance sizes are not read yet.
- Venues are fetched one after the other, about a second apart.
- Inverse (Deribit, OKX coin-margined) and linear (USDT) payoffs are compared
  on vols only; the BTC-settled payoff changes the hedge, not the vol.
- v2: USDT and USDC counted as USD; zero BTC rate and a USD discount factor of
  S / F, the same for every venue. Bybit's and Binance's price fields
  (`bid1Price`, `ask1Price`; ticker `bidPrice`, `askPrice`) were not reachable
  from the machine the second snapshot ran on.

## Next

Done in v2: one forward per expiry from prices (was step 1) and SVI per venue
with butterfly and calendar checks (was step 4).

1. Rerun v2 from Europe with all four venues.
2. Snapshot every 5 minutes for a week: how often, how large and how long
   (half-life) a dislocation on USD prices lasts.
3. Read sizes and depth, and each venue's real fee schedule: how much could
   actually be traded.
4. Price the in-the-money linear-versus-inverse gaps as a carry trade, with
   funding and margin.
5. Delta hedge with perpetuals and pay funding; simulate the vol-arb P&L with
   fees, slippage and latency.
