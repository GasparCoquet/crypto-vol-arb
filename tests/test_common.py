import math

import pandas as pd

from xvenue import black76, common


def _book(S=75000.0, F=76000.0, T=0.5, vol=0.4):
    """Two venues pricing the same smile: one linear in USD, one inverse in BTC.

    The linear venue publishes a wrong forward, as OKX's USD-margined book does.
    """
    dfac = S / F
    rows = []
    for k in range(70000, 84000, 2000):
        for cp in ("C", "P"):
            usd = dfac * black76.price(F, k, T, vol, cp == "C")
            base = dict(expiry="2027-05-07", strike=float(k), cp=cp, T=T, spot=S)
            rows.append(dict(base, venue="lin", px_ccy="USD", fwd=F * 0.988,
                             bid_px=usd * 0.999, ask_px=usd * 1.001))
            rows.append(dict(base, venue="inv", px_ccy="BTC", fwd=F,
                             bid_px=usd / S * 0.999, ask_px=usd / S * 1.001))
    return pd.DataFrame(rows), S, F, vol


def test_parity_forward_ignores_the_published_one():
    df, S, F, _ = _book()
    df = common.to_usd_today(df, S)
    pf = common.parity_forwards(df, S)
    for venue in ("lin", "inv"):
        assert abs(pf.loc["2027-05-07", venue] / F - 1) < 2e-4


def test_recomputed_vols_agree_across_conventions():
    df, S, F, vol = _book()
    df = common.to_usd_today(df, S)
    Fc = common.common_forward(df, common.parity_forwards(df, S))
    dc = common.recompute_vols(df, S, Fc)
    near = dc[(dc["strike"] / F - 1).abs() < 0.06]
    assert (near["mid_ivc"] - vol).abs().max() < 2e-3


def test_inverse_premium_is_worth_spot_times_btc():
    df = pd.DataFrame([dict(px_ccy="BTC", bid_px=0.01, ask_px=0.011),
                       dict(px_ccy="USD", bid_px=700.0, ask_px=710.0)])
    out = common.to_usd_today(df, 75000.0)
    assert math.isclose(out["bid_usd"][0], 750.0) and math.isclose(out["bid_usd"][1], 700.0)
