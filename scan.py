"""One snapshot of BTC options on Deribit, OKX, Bybit and Binance.

Matches the same option (expiry, strike, call/put) across venues and reports:
  0-3 (v1, on the vols each venue publishes):
  0. the forward each venue publishes,
  1. ATM mark IV by expiry and venue (vol points),
  2. how far each venue marks from Deribit on near-the-money strikes,
  3. crossed vol markets: bid IV on venue A above ask IV on venue B,
     gross and net of fees, fees converted into vol points through vega.
  4-7 (v2, on prices, one forward per expiry, see xvenue/common.py):
  4. the forward implied by each venue's own prices against the one it publishes,
  5. mid vol on the common forward minus Deribit, near the money,
  6. crossed markets in USD prices, gross and net of fees: the real test,
  7. SVI per venue and expiry: level, skew, curvature, butterfly and calendar checks.

Usage:  python scan.py [--save]     (--save writes data/snapshots/<UTC time>.csv.gz)
"""
import argparse
import itertools
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import numpy as np

from xvenue import black76, common, svi, venues

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
    df.loc[df["bid_px"] > df["ask_px"], ["bid_px", "ask_px"]] = None
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


def forward_check(df, pf, F):
    """Published and parity-implied forward of each venue, bps from the common forward."""
    pub = df.dropna(subset=["fwd"]).groupby(["expiry", "venue"])["fwd"].median().unstack("venue")
    ref = F.reindex(pub.index.union(pf.index))
    bps = lambda t: t.reindex(ref.index).sub(ref, axis=0).div(ref, axis=0).mul(1e4).round(0)
    return bps(pub), bps(pf)


def vs_deribit_common(dc):
    near = dc[(dc["strike"] / dc["Fc"]).between(0.9, 1.1)].dropna(subset=["mid_ivc"])
    p = near.pivot_table(index=["expiry", "strike", "cp"], columns="venue", values="mid_ivc")
    if "deribit" not in p:
        return pd.DataFrame()
    d = p.sub(p["deribit"], axis=0).drop(columns="deribit") * 100
    return pd.DataFrame({"median gap (vol pts)": d.median(), "median |gap|": d.abs().median(),
                         "strikes": d.count()}).round(2)


def crossed_usd(dc, S):
    """Bid in USD on venue A above the ask in USD on venue B, for the same option.

    Prices, not vols: no forward convention can create or remove one of these.
    The gap is shown in vol points through vega on the common forward.
    """
    rows = []
    for (expiry, k, cp), g in dc.groupby(["expiry", "strike", "cp"]):
        if g["venue"].nunique() < 2:
            continue
        F, T, dfac = g["Fc"].iloc[0], g["T"].iloc[0], g["dfac"].iloc[0]
        q = g.set_index("venue")[["bid_usd", "ask_usd", "mid_ivc"]]
        for a, b in itertools.permutations(q.index, 2):
            bid, ask = q.at[a, "bid_usd"], q.at[b, "ask_usd"]
            if pd.isna(bid) or pd.isna(ask) or bid <= ask:
                continue
            v = np.nanmean([q.at[a, "mid_ivc"], q.at[b, "mid_ivc"]])
            if np.isnan(v):
                continue
            vega_pt = dfac * black76.vega(F, k, T, v) / 100  # USD today per vol point
            fee = min(FEE_RATE * S, FEE_CAP * 0.5 * (bid + ask))  # per leg, USD
            gross = bid - ask
            rows.append(dict(expiry=expiry, strike=int(k), cp=cp, sell_on=a, buy_on=b,
                             bid_usd=round(bid, 1), ask_usd=round(ask, 1),
                             gross_usd=round(gross, 1), net_usd=round(gross - 2 * fee, 1),
                             gross_pts=round(gross / vega_pt, 2),
                             net_pts=round((gross - 2 * fee) / vega_pt, 2)))
    return pd.DataFrame(rows)


def svi_table(dc, band=0.5, min_points=6):
    """Fit SVI to each venue's out-of-the-money mid vols on the common forward."""
    q = dc.dropna(subset=["mid_ivc", "bid_ivc", "ask_ivc"]).copy()
    q["k"] = np.log(q["strike"] / q["Fc"])
    side = ((q["cp"] == "C") & (q["k"] >= 0)) | ((q["cp"] == "P") & (q["k"] <= 0))
    q = q[side & (q["k"].abs() <= band) & (q["T"] > 3 / 365)]
    rows, fits = [], {}
    for (venue, expiry), g in q.groupby(["venue", "expiry"]):
        if len(g) < min_points:
            continue
        T = g["T"].iloc[0]
        width = (g["ask_ivc"] - g["bid_ivc"]).clip(lower=0.005)
        p, rmse = svi.fit(g["k"], g["mid_ivc"], T, weight=1 / width)
        r = svi.readout(p, T, g["k"].min(), g["k"].max())
        rows.append(dict(venue=venue, expiry=expiry, n=len(g), rmse=rmse, **r))
        fits.setdefault(venue, []).append((T, p))
    t = pd.DataFrame(rows)
    cal = {v: svi.calendar_breaks(f) for v, f in fits.items()}
    return t, cal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    print(f"Snapshot {now:%Y-%m-%d %H:%M} UTC")
    load_cache = load(now)
    df = with_forward(load_cache.copy())
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

    # ---- v2: prices, one forward per expiry ----
    raw = load_cache
    S = common.snapshot_spot(raw)
    raw = common.to_usd_today(raw, S)
    pf = common.parity_forwards(raw, S)
    F = common.common_forward(raw, pf)
    dc = common.recompute_vols(raw, S, F)
    print(f"\n---- v2: every vol recomputed from prices on one forward per expiry (spot {S:,.0f}) ----")
    pub_bps, par_bps = forward_check(raw, pf, F)
    print("\n4a. Forward each venue PUBLISHES, bps from the common forward")
    print(pub_bps.head(12).to_string())
    print("\n4b. Forward each venue's PRICES imply (put-call parity), bps from the common forward")
    print(par_bps.head(12).to_string())
    print("\n5. Mid vol on the common forward minus Deribit, strikes within 10% of the forward")
    print(vs_deribit_common(dc).to_string())
    xa = crossed_usd(dc, S)
    otm_c = otm(dc.assign(F=dc["Fc"]))
    xo = crossed_usd(otm_c, S)
    n_net_usd = lambda t: int((t["net_usd"] > 0).sum()) if len(t) else 0
    print(f"\n6. Crossed markets in USD prices, fees {FEE_RATE:.2%} of spot per leg, cap {FEE_CAP:.1%} of premium:")
    print(f"   all strikes: {len(xa)} gross, {n_net_usd(xa)} net of fees")
    print(f"   out-of-the-money, |ln K/F| <= 0.25: {len(xo)} gross, {n_net_usd(xo)} net of fees")
    if len(xo):
        print(xo.sort_values("net_usd", ascending=False).head(12).to_string(index=False))
    t, cal = svi_table(dc)
    if len(t):
        print("\n7a. SVI on Deribit, by expiry (vol points; skew per +10% log-moneyness)")
        d = t[t["venue"] == "deribit"].set_index("expiry")[["n", "level", "skew", "curvature", "rmse", "butterfly_ok"]]
        print(d.round(2).to_string())
        print("\n7b. Each venue minus Deribit, median over shared expiries (vol points)")
        piv = {c: t.pivot(index="expiry", columns="venue", values=c) for c in ("level", "skew", "curvature")}
        if "deribit" in piv["level"]:
            summ = pd.DataFrame({c: piv[c].sub(piv[c]["deribit"], axis=0).drop(columns="deribit").median()
                                 for c in piv})
            summ["expiries"] = piv["level"].drop(columns="deribit").notna().sum()
            print(summ.round(2).to_string())
        print("\n7c. Arbitrage checks on the fitted smiles")
        for v, g in t.groupby("venue"):
            bf = int((~g["butterfly_ok"]).sum())
            print(f"   {v:10s} butterfly breaks {bf}/{len(g)} expiries, calendar breaks {len(cal.get(v, []))}"
                  + (f" (first between T={cal[v][0][0]:.3f} and {cal[v][0][1]:.3f}y at k={cal[v][0][2]:+.2f})"
                     if cal.get(v) else ""))
    if args.save:
        p = Path("data/snapshots")
        p.mkdir(parents=True, exist_ok=True)
        f = p / f"{now:%Y%m%dT%H%M%SZ}.csv.gz"
        dc.to_csv(f, index=False)
        print(f"\nSaved {f}")


if __name__ == "__main__":
    main()
