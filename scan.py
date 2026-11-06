"""One snapshot of BTC options on Deribit, OKX, Bybit and Binance.

Matches the same option (expiry, strike, call/put) across venues and reports:
  1. ATM mark IV by expiry and venue (vol points),
  2. how far each venue marks from Deribit on near-the-money strikes,
  3. crossed vol markets: bid IV on venue A above ask IV on venue B,
     gross and net of fees, fees converted into vol points through vega.

Usage:  python scan.py [--save]     (--save writes data/snapshots/<UTC time>.csv.gz)
"""
import argparse
import itertools
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from xvenue import black76, venues

# Assumption, first version: one taker fee per leg for every venue, a fraction of
# the underlying, capped at a fraction of the premium (Deribit's rule). Replace
# with each venue's published schedule before trusting the net numbers.
FEE_RATE = 0.0003
FEE_CAP = 0.125
SANE_IV = (0.05, 3.0)


def load(now):
    rows = []
    for name, fn in venues.LOADERS.items():
        t0 = time.time()
        try:
            got = fn(now)
            rows += got
            print(f"  {name:8s} {len(got):5d} options  ({time.time() - t0:.1f}s)")
        except Exception as e:  # one venue down must not kill the snapshot
            print(f"  {name:8s} FAILED: {e!r}")
    df = pd.DataFrame(rows)
    for c in ("bid_iv", "ask_iv", "mark_iv"):
        df.loc[~df[c].between(*SANE_IV), c] = None
    df.loc[df["bid_iv"] > df["ask_iv"], ["bid_iv", "ask_iv"]] = None  # own book crossed: bad data
    return df[df["T"] > 1 / 365].copy()  # drop the expiry inside 24h: IV unstable there


def with_forward(df):
    """One forward per expiry: median of the venues that publish one."""
    fwd = df.dropna(subset=["fwd"]).groupby("expiry")["fwd"].median()
    df["F"] = df["expiry"].map(fwd)
    return df.dropna(subset=["F"])


def forward_gaps(df):
    """Forward each venue prices its vols on, in bps from the median of the venues.

    Venues that disagree on the forward disagree on every vol by construction:
    a lower forward lifts call vols and lowers put vols for the same USD price.
    """
    f = df.dropna(subset=["fwd"]).groupby(["expiry", "venue"])["fwd"].median().unstack("venue")
    ref = f.median(axis=1)
    return f.sub(ref, axis=0).div(ref, axis=0).mul(1e4).round(0)


def atm_table(df):
    out = {}
    for expiry, g in df[df["cp"] == "C"].groupby("expiry"):
        F = g["F"].iloc[0]
        shared = g.dropna(subset=["mark_iv"]).groupby("strike")["venue"].nunique()
        shared = shared[shared >= 2]
        if shared.empty:
            continue
        k = min(shared.index, key=lambda s: abs(s - F))
        row = g[g["strike"] == k].set_index("venue")["mark_iv"] * 100
        out[(expiry, int(k))] = row
    t = pd.DataFrame(out).T
    t.index.names = ["expiry", "ATM strike"]
    return t


def vs_deribit(df):
    near = df[(df["strike"] / df["F"]).between(0.9, 1.1)].dropna(subset=["mark_iv"])
    p = near.pivot_table(index=["expiry", "strike", "cp"], columns="venue", values="mark_iv")
    if "deribit" not in p:
        return pd.DataFrame()
    d = p.sub(p["deribit"], axis=0).drop(columns="deribit") * 100
    return pd.DataFrame({"median gap (vol pts)": d.median(), "median |gap|": d.abs().median(),
                         "strikes": d.count()}).round(2)


def otm(df, band=0.25):
    """Out-of-the-money options within +-band log-moneyness of the forward.

    Deep in-the-money vols are ill-conditioned (the premium is almost all
    intrinsic, vega ~0), and each venue computes its vol with its own forward or
    rate (Binance publishes riskFreeInterest 5.3% against the spot index), so a
    few hundred dollars of forward gap becomes tens of vol points there.
    """
    m = (df["strike"] / df["F"]).map(math.log).abs()
    side = ((df["cp"] == "C") & (df["strike"] >= df["F"])) | ((df["cp"] == "P") & (df["strike"] <= df["F"]))
    return df[side & (m <= band)]


def crossed(df):
    rows = []
    for (expiry, k, cp), g in df.groupby(["expiry", "strike", "cp"]):
        if g["venue"].nunique() < 2:
            continue
        F, T = g["F"].iloc[0], g["T"].iloc[0]
        quotes = g.set_index("venue")[["bid_iv", "ask_iv"]]
        for a, b in itertools.permutations(quotes.index, 2):
            bid, ask = quotes.at[a, "bid_iv"], quotes.at[b, "ask_iv"]
            if pd.isna(bid) or pd.isna(ask) or bid <= ask:
                continue
            vol = 0.5 * (bid + ask)
            prem = black76.price(F, k, T, vol, cp == "C")
            fee = min(FEE_RATE * F, FEE_CAP * prem)  # per leg, USD
            vega_pt = black76.vega(F, k, T, vol) / 100  # USD per vol point
            fee_pts = 2 * fee / vega_pt
            rows.append(dict(expiry=expiry, strike=int(k), cp=cp, sell_on=a, buy_on=b,
                             bid_iv=round(bid * 100, 2), ask_iv=round(ask * 100, 2),
                             gross_pts=round((bid - ask) * 100, 2), fee_pts=round(fee_pts, 2),
                             net_pts=round((bid - ask) * 100 - fee_pts, 2),
                             net_usd_per_btc=round((bid - ask) * 100 * vega_pt - 2 * fee, 1)))
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    print(f"Snapshot {now:%Y-%m-%d %H:%M} UTC")
    df = with_forward(load(now))
    c = venues.DERIBIT_CHECK
    if c:
        print(f"  Deribit BTC->USD conversion kept: x {c['conversion']} "
              f"(median |IV error| vs Deribit mark, vol pts: "
              + ", ".join(f"{k} {v:.3f}" for k, v in c["median_abs_err_volpts"].items())
              + f"; {c['n_liquid']} liquid strikes)")
    pd.set_option("display.width", 160)
    print("\n0. Forward used by each venue, bps from the median (Binance publishes none)")
    print(forward_gaps(df).head(10).to_string())
    print("\n1. ATM call mark IV (vol points)")
    print(atm_table(df).round(1).head(10).to_string())
    print("\n2. Mark IV minus Deribit, strikes within 10% of the forward")
    print(vs_deribit(df).to_string())
    naive = crossed(df)
    x = crossed(otm(df))
    n_net = lambda t: int((t["net_pts"] > 0).sum()) if len(t) else 0
    print(f"\n3. Crossed vol markets (bid IV on one venue above ask IV on another), fees "
          f"{FEE_RATE:.2%} of underlying per leg, cap {FEE_CAP:.1%} of premium:")
    print(f"   all strikes (naive): {len(naive)} gross, {n_net(naive)} net of fees")
    print(f"   out-of-the-money, |ln K/F| <= 0.25: {len(x)} gross, {n_net(x)} net of fees")
    if len(x):
        print(x.sort_values("net_pts", ascending=False).head(12).to_string(index=False))
    if args.save:
        p = Path("data/snapshots")
        p.mkdir(parents=True, exist_ok=True)
        f = p / f"{now:%Y%m%dT%H%M%SZ}.csv.gz"
        df.to_csv(f, index=False)
        print(f"\nSaved {f}")


if __name__ == "__main__":
    main()
