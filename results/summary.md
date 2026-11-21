# Results, 09 Nov 2026 19:33 to 18 Nov 2026 06:58 UTC

1,363 snapshots with USD prices. Out-of-the-money options (|ln K/F| <= 0.25), crossed after fees: one taker fee per leg, 0.03% of spot, capped at 12.5% of the premium.

| Measure | Value |
|---|---|
| Crossed quotes after fees | 43,794 |
| Snapshots with at least one | 1,360 of 1,363 |
| Median gap | $20.1 per BTC (2.9 bps of spot) |
| 90th percentile, largest | $63.5, $664.5 |
| Episodes seen in one snapshot only | 54% of 11,842 |
| Longest episode | 277 snapshots (about 23 h) |

## By direction

| Direction | Crosses | Share | Median gap |
|---|---|---|---|
| USD bid > BTC ask | 43,364 | 99.0% | $20.3 |
| USD on both sides | 326 | 0.7% | $1.6 |
| BTC bid side | 104 | 0.2% | $2.3 |

## By expiry (USD bid > BTC ask)

| Expiry | Days to expiry | Crosses | Median gap | 10th to 90th percentile |
|---|---|---|---|---|
| 2026-11-13 | 1 | 45 | $0.5 | $0.4 to $1.1 |
| 2026-11-14 | 2 | 140 | $1.8 | $0.9 to $6.9 |
| 2026-11-15 | 2 | 95 | $1.4 | $0.4 to $6.6 |
| 2026-11-16 | 1 | 20 | $1.3 | $0.2 to $8.5 |
| 2026-11-17 | 2 | 56 | $14.7 | $1.3 to $29.2 |
| 2026-11-18 | 1 | 15 | $1.4 | $1.4 to $1.5 |
| 2026-11-19 | 1 | 6 | $3.5 | $1.2 to $6.7 |
| 2026-11-20 | 5 | 46 | $0.5 | $0.1 to $5.3 |
| 2026-11-27 | 14 | 124 | $3.0 | $0.4 to $5.9 |
| 2026-12-04 | 21 | 53 | $2.1 | $0.4 to $8.2 |
| 2026-12-11 | 26 | 4 | $7.7 | $7.4 to $8.2 |
| 2026-12-25 | 43 | 768 | $5.9 | $0.9 to $15.2 |
| 2027-01-29 | 77 | 8,176 | $11.0 | $1.9 to $28.8 |
| 2027-03-26 | 133 | 22,140 | $20.6 | $3.4 to $51.0 |
| 2027-06-25 | 220 | 8,551 | $35.4 | $6.8 to $89.2 |
| 2027-09-24 | 315 | 3,125 | $61.6 | $10.0 to $194.3 |

## By venue pair (top 10)

| Bid on | Ask on | Crosses | Median gap |
|---|---|---|---|
| binance | deribit | 12,749 | $23.2 |
| bybit_usdt | deribit | 9,980 | $23.8 |
| binance | okx | 8,692 | $17.9 |
| bybit_usdt | okx | 8,047 | $18.9 |
| okx_usd | okx | 2,253 | $14.4 |
| okx_usd | deribit | 1,643 | $13.2 |
| binance | okx_usd | 128 | $1.2 |
| bybit_usdt | okx_usd | 84 | $1.3 |
| okx_usd | binance | 52 | $1.6 |
| okx | binance | 36 | $3.8 |

## Episode length

| Snapshots in a row | Episodes |
|---|---|
| 1 | 6,441 |
| 2 | 2,092 |
| 3 | 1,029 |
| 4 to 6 | 1,157 |
| 7 to 12 | 542 |
| 13 to 48 | 468 |
| 49 or more | 113 |

## USD-margined over BTC-margined, per year (expiries 30+ days out)

Every out-of-the-money option quoted on both kinds of book, crossed or not: (USD-margined mid - BTC-margined mid) / BTC-margined mid / time to expiry. Median 6.2% a year over 476,555 pairs; calls 8.5%, puts 2.8%.

| Expiry | Days to expiry | Option pairs | Median per year | 25th to 75th percentile |
|---|---|---|---|---|
| 2026-12-25 | 42 | 137,364 | 7.1% | -4.8% to 20.2% |
| 2027-01-29 | 76 | 126,308 | 7.9% | 2.3% to 11.2% |
| 2027-03-26 | 133 | 114,654 | 6.0% | 3.4% to 7.6% |
| 2027-06-25 | 224 | 53,770 | 5.7% | 4.5% to 7.3% |
| 2027-09-24 | 315 | 44,459 | 5.7% | 4.6% to 6.9% |

| USD-margined | BTC-margined | Option pairs | Median per year |
|---|---|---|---|
| binance | deribit | 137,577 | 6.3% |
| binance | okx | 74,585 | 6.6% |
| bybit_usdt | deribit | 96,520 | 6.1% |
| bybit_usdt | okx | 64,380 | 6.2% |
| okx_usd | deribit | 59,510 | 5.8% |
| okx_usd | okx | 43,983 | 6.4% |

## Collector

collect.py runs: 1,362 saved, 420 failed; a saved run takes a median 18 s, the venues being read one after the other.
