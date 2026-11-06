"""Public REST snapshots of the BTC option chains of four venues, in one schema.

Each loader returns a list of dicts:
  venue, instrument, expiry ('YYYY-MM-DD', all four expire at 08:00 UTC),
  strike, cp ('C' or 'P'), T (years, 365-day), fwd (venue forward or None),
  bid_iv, ask_iv, mark_iv (decimals, None when that side is empty).

OKX, Bybit and Binance publish bid and ask implied vols. Deribit quotes inverse
options in BTC, so its bid and ask vols are solved here with Black-76 (see
deribit()). No API key is needed for any of these endpoints.
"""
import json
import statistics
import urllib.request
from datetime import datetime, timezone

from . import black76

_UA = {"User-Agent": "crypto-vol-arb research script"}
_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# Filled by deribit(): which BTC->USD conversion reproduces Deribit's own mark IV.
DERIBIT_CHECK = {}


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=20) as r:
        return json.loads(r.read())


def _num(x):
    """float, or None for a missing quote. Venues send 0 for an empty side."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _exp_dmy(s):  # '25DEC26' or '7NOV26'
    return f"20{s[-2:]}-{_MONTHS[s[-5:-2]]:02d}-{int(s[:-5]):02d}"


def _exp_ymd(s):  # '261225'
    return f"20{s[:2]}-{s[2:4]}-{s[4:6]}"


def _years(expiry, now):
    t = datetime.strptime(expiry, "%Y-%m-%d").replace(hour=8, tzinfo=timezone.utc)
    return (t - now).total_seconds() / (365.0 * 86400)


def deribit(now):
    """Inverse options: premium in BTC, payoff max(S-K, 0)/S BTC.

    To solve an IV the BTC premium is turned into USD. Two candidates: times the
    index (spot) or times the expiry's forward. The one that reproduces Deribit's
    published mark_iv on liquid strikes is kept, and the check is reported.
    """
    rows = _get("https://www.deribit.com/api/v2/public/get_book_summary_by_currency"
                "?currency=BTC&kind=option")["result"]
    out = []
    for r in rows:
        _, e, k, cp = r["instrument_name"].split("-")
        expiry = _exp_dmy(e)
        F, S = _num(r.get("underlying_price")), _num(r.get("estimated_delivery_price"))
        T = _years(expiry, now)
        if F is None or S is None or T <= 0:
            continue
        mark_iv = _num(r.get("mark_iv"))
        out.append(dict(venue="deribit", instrument=r["instrument_name"], expiry=expiry,
                        strike=float(k), cp=cp, T=T, fwd=F, index=S,
                        bid_btc=_num(r.get("bid_price")), ask_btc=_num(r.get("ask_price")),
                        mark_btc=_num(r.get("mark_price")),
                        mark_iv=mark_iv / 100 if mark_iv else None))

    def solve(r, p_btc, conv):
        if p_btc is None:
            return None
        usd = p_btc * (r["index"] if conv == "index" else r["fwd"])
        return black76.implied_vol(usd, r["fwd"], r["strike"], r["T"], r["cp"] == "C")

    liquid = [r for r in out if r["mark_iv"] and r["mark_btc"] and r["T"] > 7 / 365
              and 0.85 < r["strike"] / r["fwd"] < 1.15]
    err = {}
    for conv in ("index", "fwd"):
        d = [abs(solve(r, r["mark_btc"], conv) - r["mark_iv"]) * 100
             for r in liquid if solve(r, r["mark_btc"], conv) is not None]
        err[conv] = statistics.median(d) if d else float("inf")
    conv = min(err, key=err.get)
    DERIBIT_CHECK.update(conversion=conv, median_abs_err_volpts=err, n_liquid=len(liquid))

    for r in out:
        r["bid_iv"] = solve(r, r.pop("bid_btc"), conv)
        r["ask_iv"] = solve(r, r.pop("ask_btc"), conv)
        r.pop("mark_btc")
        r.pop("index")
    return out


def okx(now):
    """Two families come back: BTC-USD (coin-margined) and BTC-USD_UM (USD-margined)."""
    rows = _get("https://www.okx.com/api/v5/public/opt-summary?uly=BTC-USD")["data"]
    out = []
    for r in rows:
        fam, e, k, cp = r["instId"].rsplit("-", 3)
        expiry = _exp_ymd(e)
        out.append(dict(venue="okx_usd" if fam.endswith("_UM") else "okx",
                        instrument=r["instId"], expiry=expiry, strike=float(k), cp=cp,
                        T=_years(expiry, now), fwd=_num(r.get("fwdPx")),
                        bid_iv=_num(r.get("bidVol")), ask_iv=_num(r.get("askVol")),
                        mark_iv=_num(r.get("markVol"))))
    return out


def bybit(now):
    """Symbols like BTC-20NOV26-82000-C-USDT; the settle suffix is kept in the venue name."""
    rows = _get("https://api.bybit.com/v5/market/tickers?category=option&baseCoin=BTC")["result"]["list"]
    out = []
    for r in rows:
        parts = r["symbol"].split("-")
        expiry = _exp_dmy(parts[1])
        venue = "bybit" if len(parts) == 4 else "bybit_" + parts[4].lower()
        out.append(dict(venue=venue, instrument=r["symbol"], expiry=expiry,
                        strike=float(parts[2]), cp=parts[3], T=_years(expiry, now),
                        fwd=_num(r.get("underlyingPrice")),
                        bid_iv=_num(r.get("bid1Iv")), ask_iv=_num(r.get("ask1Iv")),
                        mark_iv=_num(r.get("markIv"))))
    return out


def binance(now):
    rows = [r for r in _get("https://eapi.binance.com/eapi/v1/mark") if r["symbol"].startswith("BTC-")]
    out = []
    for r in rows:
        _, e, k, cp = r["symbol"].split("-")
        expiry = _exp_ymd(e)
        out.append(dict(venue="binance", instrument=r["symbol"], expiry=expiry, strike=float(k),
                        cp=cp, T=_years(expiry, now), fwd=None,
                        bid_iv=_num(r.get("bidIV")), ask_iv=_num(r.get("askIV")),
                        mark_iv=_num(r.get("markIV"))))
    return out


LOADERS = {"deribit": deribit, "okx": okx, "bybit": bybit, "binance": binance}
