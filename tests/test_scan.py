import pytest

import scan


def test_load_says_when_no_venue_answers(monkeypatch):
    def down(now):
        raise OSError("network unreachable")

    monkeypatch.setattr(scan.venues, "LOADERS", {"deribit": down, "okx": down})
    with pytest.raises(RuntimeError, match="no venue answered"):
        scan.load(None)
