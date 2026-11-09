import numpy as np

from xvenue import svi

P0 = (0.02, 0.10, -0.3, 0.0, 0.15)
T = 0.25


def test_fit_recovers_a_clean_smile():
    k = np.linspace(-0.4, 0.4, 25)
    iv = svi.vol(P0, k, T)
    p, rmse = svi.fit(k, iv, T)
    assert rmse < 0.05  # vol points
    r = svi.readout(p, T, -0.4, 0.4)
    assert abs(r["level"] - svi.vol(P0, [0.0], T)[0] * 100) < 0.05
    assert r["skew"] < 0 and r["curvature"] > 0 and r["butterfly_ok"]


def test_calendar_break_is_detected():
    later_but_lower = (0.005, 0.10, -0.3, 0.0, 0.15)  # less total variance at a longer maturity
    assert svi.calendar_breaks([(0.25, P0), (0.5, later_but_lower)])
    assert not svi.calendar_breaks([(0.25, P0), (0.5, (0.04, 0.12, -0.3, 0.0, 0.15))])
