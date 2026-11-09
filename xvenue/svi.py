"""Raw SVI fit of one smile (one venue, one expiry) and the checks a vol book runs on it.

Total variance w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2)),
with k = ln(K / F) and w = vol^2 * T.

The five parameters are fitted, then read back as three numbers a desk hedges
and attributes P&L on:
  level      ATM vol, vol(k = 0)
  skew       (vol(+0.1) - vol(-0.1)) / 2: vol points per +10% of log-moneyness
  curvature  vol(+0.1) + vol(-0.1) - 2 vol(0): how far the wings sit above ATM
Checks:
  butterfly  Gatheral's g(k) >= 0 across the fitted strikes (no negative density)
  calendar   total variance rises with maturity at every k (done across expiries)
"""
import math

import numpy as np
from scipy.optimize import least_squares


def w(params, k):
    a, b, rho, m, sig = params
    k = np.asarray(k, dtype=float)
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sig ** 2))


def vol(params, k, T):
    return np.sqrt(np.maximum(w(params, k), 1e-12) / T)


def g(params, k):
    """Gatheral's density condition; negative means butterfly arbitrage at k."""
    a, b, rho, m, sig = params
    k = np.asarray(k, dtype=float)
    s = np.sqrt((k - m) ** 2 + sig ** 2)
    ww = w(params, k)
    w1 = b * (rho + (k - m) / s)
    w2 = b * sig ** 2 / s ** 3
    return (1 - k * w1 / (2 * ww)) ** 2 - (w1 ** 2 / 4) * (1 / ww + 0.25) + w2 / 2


def fit(k, iv, T, weight=None):
    """Least squares in vol, weighted (e.g. by 1 / bid-ask width). Returns params and RMSE in vol points."""
    k, iv = np.asarray(k, float), np.asarray(iv, float)
    wt = np.ones_like(iv) if weight is None else np.asarray(weight, float)
    w_obs = iv ** 2 * T

    def resid(p):
        a, b, rho, m, sig = p
        floor = a + b * sig * math.sqrt(max(1 - rho * rho, 0.0))  # minimum total variance
        pen = 0.0 if floor > 0 else 1e3 * -floor
        return np.append((vol(p, k, T) - iv) * wt, pen)

    best = None
    for rho0 in (-0.5, 0.0, 0.5):
        x0 = [0.5 * w_obs.min(), 0.1, rho0, 0.0, 0.1]
        lo = [-w_obs.max(), 0.0, -0.999, -1.0, 1e-3]
        hi = [w_obs.max(), 5.0, 0.999, 1.0, 2.0]
        r = least_squares(resid, x0, bounds=(lo, hi), max_nfev=4000)
        if best is None or r.cost < best.cost:
            best = r
    p = best.x
    rmse = float(np.sqrt(np.mean((vol(p, k, T) - iv) ** 2)) * 100)
    return p, rmse


def readout(p, T, k_lo, k_hi):
    v = lambda x: float(vol(p, [x], T)[0]) * 100
    grid = np.linspace(k_lo, k_hi, 101)
    gmin = float(np.min(g(p, grid)))
    return dict(level=v(0.0), skew=(v(0.1) - v(-0.1)) / 2,
                curvature=v(0.1) + v(-0.1) - 2 * v(0.0),
                g_min=gmin, butterfly_ok=gmin >= 0)


def calendar_breaks(fits, k_grid=np.linspace(-0.3, 0.3, 61)):
    """fits: list of (T, params) for one venue. Count consecutive pairs where w falls with T."""
    fits = sorted(fits, key=lambda x: x[0])
    bad = []
    for (T1, p1), (T2, p2) in zip(fits, fits[1:]):
        drop = w(p1, k_grid) - w(p2, k_grid)
        if np.max(drop) > 1e-6:
            bad.append((T1, T2, float(k_grid[int(np.argmax(drop))])))
    return bad
