"""Black-76 on the forward: price, vega and implied vol.

Crypto option venues quote implied vols against the forward of each expiry, with
rates near zero, so the discount factor defaults to 1.
"""
import math

_SQ2 = math.sqrt(2.0)
_SQ2PI = math.sqrt(2.0 * math.pi)


def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / _SQ2))


def npdf(x):
    return math.exp(-0.5 * x * x) / _SQ2PI


def price(F, K, T, vol, is_call, df=1.0):
    """Black-76 premium in the quote currency of F and K."""
    if T <= 0 or vol <= 0:
        return df * (max(F - K, 0.0) if is_call else max(K - F, 0.0))
    s = vol * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    d2 = d1 - s
    if is_call:
        return df * (F * ncdf(d1) - K * ncdf(d2))
    return df * (K * ncdf(-d2) - F * ncdf(-d1))


def vega(F, K, T, vol, df=1.0):
    """dPrice/dvol per 1.00 of vol. Divide by 100 for one vol point."""
    s = vol * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * s * s) / s
    return df * F * math.sqrt(T) * npdf(d1)


def implied_vol(p, F, K, T, is_call, df=1.0, lo=1e-4, hi=5.0):
    """Vol that reprices p. Newton first, bisection if Newton leaves [lo, hi].

    Returns None when p is outside the no-arbitrage bounds (below intrinsic or
    above the forward/strike), where no vol can reprice it.
    """
    if p is None or T <= 0:
        return None
    intrinsic = df * (max(F - K, 0.0) if is_call else max(K - F, 0.0))
    upper = df * (F if is_call else K)
    if not (intrinsic < p < upper):
        return None
    vol = 0.6  # typical BTC vol: a safe start for Newton
    for _ in range(100):
        v = vega(F, K, T, vol, df)
        if v < 1e-14:
            break
        step = (price(F, K, T, vol, is_call, df) - p) / v
        nv = vol - step
        if not (lo < nv < hi):
            break
        vol = nv
        if abs(step) < 1e-12:
            return vol
    a, b = lo, hi  # price is increasing in vol, so bisection always converges
    for _ in range(200):
        m = 0.5 * (a + b)
        if price(F, K, T, m, is_call, df) < p:
            a = m
        else:
            b = m
        if b - a < 1e-12:
            break
    return 0.5 * (a + b)
