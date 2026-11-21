"""BTC perpetual funding over the week of snapshots, annualised: the rate to set against the options carry.

Public endpoints, no API key. Each venue's funding prints over the window are summed and scaled
to a year. Writes results/funding.md.

Usage:  python funding.py
"""
import datetime as dt
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
START = dt.datetime(2026, 11, 9, 19, 33, tzinfo=dt.timezone.utc)  # first snapshot with USD prices
END = dt.datetime(2026, 11, 18, 7, 0, tzinfo=dt.timezone.utc)  # last one
S, E = int(START.timestamp() * 1000), int(END.timestamp() * 1000)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def binance():
    rows = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime={S}&endTime={E}&limit=1000")
    return [float(x["fundingRate"]) for x in rows]


def bybit():
    url = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&startTime={S}&endTime={E}&limit=200"
    return [float(x["fundingRate"]) for x in get(url)["result"]["list"]]


def okx():  # the endpoint returns the latest 100 prints (about a month); keep the window
    rows = get("https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100")["data"]
    return [float(x["realizedRate"] or x["fundingRate"]) for x in rows if S <= int(x["fundingTime"]) <= E]


def deribit():  # inverse perpetual, funding accrues every hour
    url = (f"https://www.deribit.com/api/v2/public/get_funding_rate_history?instrument_name=BTC-PERPETUAL"
           f"&start_timestamp={S}&end_timestamp={E}")
    return [float(x["interest_1h"]) for x in get(url)["result"]]


def main():
    days = (END - START).total_seconds() / 86400
    lines = ["| Perpetual | Margin | Funding prints | Annualised |", "|---|---|---|---|"]
    for name, margin, fn in [("Binance BTCUSDT", "USDT", binance), ("Bybit BTCUSDT", "USDT", bybit),
                             ("OKX BTC-USDT-SWAP", "USDT", okx), ("Deribit BTC-PERPETUAL", "BTC", deribit)]:
        try:
            rates = fn()
            lines.append(f"| {name} | {margin} | {len(rates)} | {sum(rates) / days * 365:.1%} |")
        except Exception as e:  # one venue down must not hide the others
            lines.append(f"| {name} | {margin} | failed: {e!r} | |")
    text = f"# BTC perpetual funding, {START:%d %b %H:%M} to {END:%d %b %Y %H:%M} UTC ({days:.1f} days)\n\n"
    text += "\n".join(lines) + "\n"
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "funding.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
