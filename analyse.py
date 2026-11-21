"""A week of snapshots: crossed BTC option markets across venues, on USD prices.

Reads every data/snapshots/*.csv.gz written by `scan.py --save` (collect.py runs it
every 5 minutes) and measures how often one venue's bid sits above another venue's
ask for the same option, by how much after fees, in which direction, at which
expiries and for how long. Writes results/summary.md and results/gap_vs_expiry.png.

Usage:  python analyse.py
"""
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scan import FEE_CAP, FEE_RATE

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results"
INVERSE = {"deribit", "okx"}  # premium and margin in BTC; okx_usd, bybit_usdt and binance are in USD or USDT
BAND = 0.25  # out of the money: |ln K/F| <= 0.25
PAUSE = np.timedelta64(8, "m")  # snapshots are 5 minutes apart: a longer pause ends an episode
KEY = ["expiry", "strike", "cp"]
MAIN = "USD bid > BTC ask"


def crosses(path):
    """Every case of one venue bidding above another venue's ask for the same option, in USD."""
    d = pd.read_csv(path)
    if "spot" not in d:  # the first snapshots (v1) kept no USD prices
        return None
    S = d["spot"].median()
    bids = d[KEY + ["venue", "bid_usd", "mid_ivc", "Fc", "T"]].dropna(subset=["bid_usd"])
    asks = d[KEY + ["venue", "ask_usd", "mid_ivc"]].dropna(subset=["ask_usd"])
    m = bids.merge(asks, on=KEY, suffixes=("_bid", "_ask"))
    m = m[(m.venue_bid != m.venue_ask) & (m.bid_usd > m.ask_usd)]
    m = m[m.mid_ivc_bid.notna() | m.mid_ivc_ask.notna()].copy()  # no vol on either side: a broken quote
    fee = np.minimum(FEE_RATE * S, FEE_CAP * (m.bid_usd + m.ask_usd) / 2)  # one taker fee per leg
    m["net"] = m.bid_usd - m.ask_usd - 2 * fee
    lm = np.log(m.strike / m.Fc)
    m["otm"] = (((m.cp == "C") & (lm >= 0)) | ((m.cp == "P") & (lm <= 0))) & (lm.abs() <= BAND)
    m["ts"] = pd.to_datetime(Path(path).name[:16], format="%Y%m%dT%H%M%SZ")
    m["spot"] = S
    return m


def direction(x):
    """Which kind of book bids above which: USD-margined (linear) or BTC-margined (inverse)."""
    usd_bid, usd_ask = ~x.venue_bid.isin(INVERSE), ~x.venue_ask.isin(INVERSE)
    return np.select([usd_bid & ~usd_ask, usd_bid & usd_ask], [MAIN, "USD on both sides"], "BTC bid side")


def episodes(x):
    """Length, in snapshots, of each run in which one option stays crossed between the same two venues."""
    runs = []
    for _, g in x.groupby(KEY + ["venue_bid", "venue_ask"]):
        t = np.unique(g.ts.values)
        start = prev = t[0]
        for u in t[1:]:
            if u - prev > PAUSE:
                runs.append((start, prev))
                start = u
            prev = u
        runs.append((start, prev))
    return pd.Series([int(round((e - s) / np.timedelta64(5, "m"))) + 1 for s, e in runs])


def collector(log):
    """Runs logged by collect.py: saved, failed, median seconds of a saved run."""
    ok, failed, secs = 0, 0, []
    for line in open(log, encoding="utf-8", errors="replace"):
        m = re.match(r"\S+ \S+Z\s+([\d.]+)s\s+(\S+)", line)
        if m and m[2] == "ok":
            ok += 1
            secs.append(float(m[1]))
        elif m:
            failed += 1
    return ok, failed, float(np.median(secs)) if secs else float("nan")


def chart(by_exp):
    """Median gap per expiry on a linear time axis: if it is carry, it grows with time to expiry."""
    e = by_exp[by_exp.crosses >= 100].sort_values("days")
    ink, muted, blue, ground = "#0b0b0b", "#898781", "#2a78d6", "#fcfcfb"
    fig, ax = plt.subplots(figsize=(11, 6.6), dpi=150)
    fig.patch.set_facecolor(ground)
    ax.set_facecolor(ground)
    ax.plot(e.days, e["median"], color=blue, lw=2, zorder=2)
    ax.scatter(e.days, e["median"], s=70, color=blue, edgecolors=ground, linewidths=1.5, zorder=3)
    big = e[e.crosses >= 1000]
    for exp, r in big.iterrows():
        ax.text(r.days + 6, r["median"] - 3.2, f"{pd.Timestamp(exp):%b %Y}  ${r['median']:.0f}",
                ha="left", va="top", color=ink, fontsize=11)
    rest = e.drop(big.index)
    if len(rest):
        ax.text(rest.days.mean() + 4, rest["median"].max() + 9,
                f"Shorter expiries\n${rest['median'].min():.0f} to ${rest['median'].max():.0f}",
                ha="center", va="bottom", color=ink, fontsize=11, linespacing=1.4)
    per_month = (e["median"].iloc[-1] - e["median"].iloc[0]) / (e.days.iloc[-1] - e.days.iloc[0]) * 365 / 12
    top = e["median"].max() * 1.2
    ax.text(8, top * 0.87, f"About ${per_month:.0f} more per BTC\nfor each extra month to expiry",
            ha="left", va="top", color=ink, fontsize=13, fontweight="bold", linespacing=1.4)
    ax.set_xlim(-8, 380)
    ax.set_ylim(0, top)
    ax.set_xticks([0, 91, 182, 273, 365])
    ax.set_xticklabels(["now", "3 months", "6 months", "9 months", "1 year"])
    ax.yaxis.set_major_formatter(lambda v, _: f"${v:.0f}")
    ax.set_xlabel("Time to expiry", color=muted, labelpad=8)
    ax.set_ylabel("Median gap after fees, USD per BTC", color=muted, labelpad=8)
    ax.tick_params(colors=muted, length=0, pad=6)
    ax.grid(True, axis="y", color="#e1e0d9", lw=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#c3c2b7")
    fig.text(0.07, 0.94, "The longer the option, the bigger the gap", fontsize=17, fontweight="bold", color=ink)
    fig.text(0.07, 0.895, "Out-of-the-money BTC options where a USD-margined bid sits above a BTC-margined ask, "
             "median per expiry date", fontsize=10.5, color=muted)
    fig.text(0.07, 0.025, f"Expiries with 100 or more crosses ({int(e.crosses.sum()):,} crosses). A pricing error "
             "would not depend on the expiry; a financing cost grows with it.", fontsize=9.5, color=muted)
    fig.subplots_adjust(left=0.07, right=0.975, top=0.85, bottom=0.15)
    return fig


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def load_crosses():
    """All snapshots: (how many, first time, last time, out-of-the-money crosses still positive after fees)."""
    files = sorted((ROOT / "data" / "snapshots").glob("*.csv.gz"))
    parts = [m for m in map(crosses, files) if m is not None]
    x = pd.concat(parts)
    n = x[x.otm & (x.net > 0)].copy()
    n["direction"] = direction(n)
    n["days"] = n["T"] * 365
    return len(parts), x.ts.min(), x.ts.max(), n


def by_expiry(n):
    return n[n.direction == MAIN].groupby("expiry").agg(
        days=("days", "median"), crosses=("net", "size"), median=("net", "median"),
        p10=("net", lambda s: s.quantile(0.1)), p90=("net", lambda s: s.quantile(0.9)))


def main():
    snaps, first, last, n = load_crosses()
    by_dir = n.groupby("direction").net.agg(["size", "median"]).sort_values("size", ascending=False)
    by_exp = by_expiry(n)
    by_pair = n.groupby(["venue_bid", "venue_ask"]).net.agg(["size", "median"]).sort_values("size", ascending=False)
    ep = episodes(n)
    ok, failed, secs = collector(ROOT / "data" / "collect.log")
    usd = lambda v: f"${v:,.1f}"

    text = [
        f"# Results, {first:%d %b %Y %H:%M} to {last:%d %b %Y %H:%M} UTC",
        f"{snaps:,} snapshots with USD prices. Out-of-the-money options (|ln K/F| <= {BAND}), crossed after "
        f"fees: one taker fee per leg, {FEE_RATE:.2%} of spot, capped at {FEE_CAP:.1%} of the premium.",
        md_table(["Measure", "Value"], [
            ["Crossed quotes after fees", f"{len(n):,}"],
            ["Snapshots with at least one", f"{n.ts.nunique():,} of {snaps:,}"],
            ["Median gap", f"{usd(n.net.median())} per BTC ({(n.net / n.spot * 1e4).median():.1f} bps of spot)"],
            ["90th percentile, largest", f"{usd(n.net.quantile(0.9))}, {usd(n.net.max())}"],
            ["Episodes seen in one snapshot only", f"{(ep == 1).mean():.0%} of {len(ep):,}"],
            ["Longest episode", f"{ep.max()} snapshots (about {ep.max() * 5 / 60:.0f} h)"],
        ]),
        "## By direction",
        md_table(["Direction", "Crosses", "Share", "Median gap"],
                 [[d, f"{int(r['size']):,}", f"{r['size'] / len(n):.1%}", usd(r["median"])] for d, r in by_dir.iterrows()]),
        f"## By expiry ({MAIN})",
        md_table(["Expiry", "Days to expiry", "Crosses", "Median gap", "10th to 90th percentile"],
                 [[e, f"{r.days:.0f}", f"{int(r.crosses):,}", usd(r['median']), f"{usd(r.p10)} to {usd(r.p90)}"]
                  for e, r in by_exp.sort_index().iterrows()]),
        "## By venue pair (top 10)",
        md_table(["Bid on", "Ask on", "Crosses", "Median gap"],
                 [[a, b, f"{int(r['size']):,}", usd(r["median"])] for (a, b), r in by_pair.head(10).iterrows()]),
        "## Episode length",
        md_table(["Snapshots in a row", "Episodes"],
                 [[label, f"{((ep >= lo) & (ep <= hi)).sum():,}"] for label, lo, hi in
                  [("1", 1, 1), ("2", 2, 2), ("3", 3, 3), ("4 to 6", 4, 6), ("7 to 12", 7, 12),
                   ("13 to 48", 13, 48), ("49 or more", 49, 10**9)]]),
        "## Collector",
        f"collect.py runs: {ok:,} saved, {failed:,} failed; a saved run takes a median {secs:.0f} s, "
        "the venues being read one after the other.",
    ]
    OUT.mkdir(exist_ok=True)
    (OUT / "summary.md").write_text("\n\n".join(text) + "\n", encoding="utf-8")
    chart(by_exp).savefig(OUT / "gap_vs_expiry.png", facecolor="#fcfcfb")
    print((OUT / "summary.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
