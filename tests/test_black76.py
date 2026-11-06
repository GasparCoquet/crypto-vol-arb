from xvenue import black76

F = 76000.0


def test_put_call_parity():
    K, T, v = 80000.0, 0.25, 0.45
    c = black76.price(F, K, T, v, True)
    p = black76.price(F, K, T, v, False)
    assert abs((c - p) - (F - K)) < 1e-8


def test_implied_vol_round_trip():
    # Out-of-the-money side only, as a surface is built. A deep in-the-money
    # price is almost all intrinsic (K=50k call at 20% vol: 26000.0000), so its
    # vega is ~0 and the vol is ill-conditioned: a 1e-8 price error moves it 2e-6.
    for K in (50000.0, 76000.0, 120000.0):
        for v in (0.2, 0.5, 1.2):
            for call in (True, False):
                if (call and K < F) or (not call and K > F):
                    continue
                p = black76.price(F, K, 0.1, v, call)
                if p < 1.0:  # below one dollar on a 76k underlying: no usable quote
                    continue
                iv = black76.implied_vol(p, F, K, 0.1, call)
                assert abs(iv - v) < 1e-7, (K, v, call, iv)


def test_no_vol_outside_bounds():
    assert black76.implied_vol(1.0, F, 70000.0, 0.1, True) is None  # below intrinsic 6000
    assert black76.implied_vol(F + 1, F, 70000.0, 0.1, True) is None  # above the forward


def test_vega_matches_finite_difference():
    K, T, v, h = 90000.0, 0.3, 0.5, 1e-5
    fd = (black76.price(F, K, T, v + h, True) - black76.price(F, K, T, v - h, True)) / (2 * h)
    assert abs(black76.vega(F, K, T, v) - fd) < 1e-6 * fd
