"""One forward per expiry, implied by prices rather than by each venue's convention.

v1 compared the implied vols each venue publishes. Those vols are computed on
each venue's own forward, so a venue with a lower forward shows rich calls and
cheap puts at the same USD price. Here every vol is recomputed from prices:

1. Every premium is turned into USD today. Linear options (USD, USDT, USDC) are
   taken as quoted. Inverse options (premium in BTC) are multiplied by the spot
   index: the BTC you receive today is worth premium x spot today.
2. Each venue's forward is backed out of its own prices by put-call parity.
   With a zero BTC rate and a USD discount factor df = S / F, both inverse and
   linear books give the same relation, x = (C - P) / S = 1 - K / F, so
   F = K / (1 - x).
3. The forward of an expiry is the median of the venues' parity forwards.
4. Every bid, ask and mid is turned back into a Black-76 vol on that one forward
   and one discount factor, so two vols differ only if two prices differ.
"""
import math

import pandas as pd

from . import black76


def snapshot_spot(df):
    """BTC index for the snapshot: Deribit's if present, else the median of the venues."""
    d = df.loc[df["venue"] == "deribit", "spot"].dropna()
    s = d if len(d) else df["spot"].dropna()
    return float(s.median()) if len(s) else None


def to_usd_today(df, S):
    """bid_usd, ask_usd: what the premium is worth in USD today."""
    mult = df["px_ccy"].map({"BTC": S, "USD": 1.0})
    df["bid_usd"] = df["bid_px"] * mult
    df["ask_usd"] = df["ask_px"] * mult
    return df


def parity_forwards(df, S, band=0.10):
    """Forward implied by each venue's own call and put mids, per expiry, by venue.

    Uses strikes within +-band of a first guess of the forward (the published
    median, else the spot) where both the call and the put have a bid and an ask.
    Returns a DataFrame indexed by expiry with one column per venue.
    """
    guess = df.dropna(subset=["fwd"]).groupby("expiry")["fwd"].median()
    mid = 0.5 * (df["bid_usd"] + df["ask_usd"])
    q = df.assign(mid=mid).dropna(subset=["mid"])
    out = {}
    for (venue, expiry), g in q.groupby(["venue", "expiry"]):
        F0 = guess.get(expiry, S)
        g = g[(g["strike"] / F0 - 1).abs() <= band]
        c = g[g["cp"] == "C"].set_index("strike")["mid"]
        p = g[g["cp"] == "P"].set_index("strike")["mid"]
        k = c.index.intersection(p.index)
        if len(k) == 0:
            continue
        x = (c[k] - p[k]) / S
        F = (k.to_series() / (1 - x)).where(x < 1)
        F = F[(F / F0 - 1).abs() <= band]  # a crossed or stale pair can throw it far off
        if len(F):
            out[(expiry, venue)] = float(F.median())
    if not out:
        return pd.DataFrame()
    return pd.Series(out).unstack()


def common_forward(df, pf):
    """One forward per expiry: median of the venues' parity forwards, else of the published ones."""
    published = df.dropna(subset=["fwd"]).groupby("expiry")["fwd"].median()
    parity = pf.median(axis=1) if len(pf) else pd.Series(dtype=float)
    F = published.copy()
    F.update(parity)
    for e in parity.index.difference(F.index):
        F[e] = parity[e]
    return F


def recompute_vols(df, S, F):
    """bid_ivc, ask_ivc, mid_ivc: Black-76 vols from USD prices on one forward and df = S/F."""
    df = df.copy()
    df["Fc"] = df["expiry"].map(F)
    df = df.dropna(subset=["Fc"])
    df["dfac"] = S / df["Fc"]

    def iv(p, r):
        if p is None or (isinstance(p, float) and math.isnan(p)):
            return None
        return black76.implied_vol(p / r["dfac"], r["Fc"], r["strike"], r["T"], r["cp"] == "C")

    df["bid_ivc"] = [iv(r["bid_usd"], r) for _, r in df.iterrows()]
    df["ask_ivc"] = [iv(r["ask_usd"], r) for _, r in df.iterrows()]
    mid = 0.5 * (df["bid_usd"] + df["ask_usd"])
    df["mid_ivc"] = [iv(m, r) for m, (_, r) in zip(mid, df.iterrows())]
    for c in ("bid_ivc", "ask_ivc", "mid_ivc"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
