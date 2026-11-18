"""Pins the flagged queue-delay proxy candidate's arithmetic and labeling.

The proxy is not an accepted metric: these tests exist to make sure it can
never silently become one (label check) and that its arithmetic, negative
handling and caveat reporting stay exactly as documented.
"""

import pytest

from analysis.candidates.queue_delay_proxy import (
    PROXY_LABEL,
    queue_delay_proxy,
)


def test_arithmetic_and_label():
    out = queue_delay_proxy([0.040, 0.050, 0.038], 37.5e-3)
    assert out["metric_name"] == PROXY_LABEL
    assert "queue_delay_proxy_ms" in PROXY_LABEL
    assert PROXY_LABEL != "queue_delay_ms"
    assert out["n"] == 3
    # median of (2.5, 12.5, 0.5) ms is 2.5 ms
    assert out["median_ms"] == pytest.approx(2.5)


def test_negatives_are_counted_not_clamped():
    # residence below the configured base (negative jitter draw) must surface
    out = queue_delay_proxy([0.037, 0.036, 0.050], 37.5e-3)
    assert out["negative_count"] == 2


def test_caveats_always_present():
    out = queue_delay_proxy([0.040], 37.5e-3)
    assert len(out["caveats"]) == 4
    assert any("understate" in c for c in out["caveats"])


def test_empty_series_has_no_stats():
    out = queue_delay_proxy([], 37.5e-3)
    assert out["n"] == 0
    assert "median_ms" not in out
