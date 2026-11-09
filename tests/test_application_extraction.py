import numpy as np
import pandas as pd
import pytest

from scripts.extract_sdncampus_distributions import (
    SDNCAMPUS_ASSETS,
    summarize_flow_frame,
)
from scripts.extract_sdncampus_transfer_summaries import (
    classify_flow_end,
    heldout_parity,
    record_split_keys,
    summarize_transfer_file,
)


def test_sdncampus_summary_converts_cic_duration_microseconds():
    frame = pd.DataFrame(
        {
            "Flow Duration": [1_000_000, 2_000_000, 0],
            "Total Length of Fwd Packet": [100.0, 200.0, 50.0],
            "Total Length of Bwd Packet": [300.0, 600.0, 50.0],
            "Total Fwd Packet": [1, 2, 1],
            "Total Bwd packets": [3, 6, 1],
        }
    )

    result = summarize_flow_frame(
        frame,
        SDNCAMPUS_ASSETS["voip"],
        bootstrap_replicates=20,
        rng=np.random.default_rng(1),
    )

    assert result["flow_rows"] == 3
    assert result["zero_duration_rows"] == 1
    assert result["duration_median_s"] == 1.0
    assert result["total_bytes_median"] == 400.0
    assert result["flow_mbps_median"] == pytest.approx(0.0032)
    assert result["downlink_byte_fraction_median"] == 0.75


def test_sdncampus_summary_rejects_incomplete_schema():
    with pytest.raises(ValueError, match="missing columns"):
        summarize_flow_frame(
            pd.DataFrame({"Flow Duration": [1.0]}),
            SDNCAMPUS_ASSETS["voip"],
            bootstrap_replicates=5,
            rng=np.random.default_rng(1),
        )


def _transfer_sample(n: int, start: int, ended: bool) -> pd.DataFrame:
    ids = np.arange(start, start + n)
    frame = pd.DataFrame(
        {
            "Flow ID": [f"10.0.0.1-10.0.0.2-99-{i}" for i in ids],
            "Flow Duration": np.full(n, 1_000_000.0),
            "Total Length of Fwd Packet": np.full(n, 100.0),
            "Total Length of Bwd Packet": np.full(n, 400.0),
            "FIN Flag Count": np.full(n, 1 if ended else 0, dtype=float),
            "RST Flag Count": np.zeros(n, dtype=float),
        }
    )
    return frame


def split_keys_sample(n: int, start: int) -> pd.DataFrame:
    ids = np.arange(start, start + n)
    return pd.DataFrame(
        {
            "Flow Duration": np.full(n, 1_000_000.0),
            "Total Length of Fwd Packet": ids.astype(float),
            "Total Length of Bwd Packet": np.full(n, 400.0),
            "FIN Flag Count": np.zeros(n, dtype=float),
            "RST Flag Count": np.zeros(n, dtype=float),
        }
    )


def test_transfer_split_is_deterministic_and_not_degenerate():
    frame = split_keys_sample(50, 0)
    left = heldout_parity(record_split_keys(frame), 1234)
    right = heldout_parity(record_split_keys(frame), 1234)
    assert np.array_equal(left, right)
    assert 5 < left.sum() < 45  # split is not degenerate


def test_transfer_end_classification():
    frame = _transfer_sample(10, 0, ended=True)
    frame.loc[0:4, ["FIN Flag Count", "RST Flag Count"]] = (0, 0)
    kinds = classify_flow_end(frame["FIN Flag Count"], frame["RST Flag Count"])
    assert (kinds[:5] == "censored").all()
    assert (kinds[5:] == "fin_rst").all()


def test_transfer_summary_reports_both_halves_and_ends():
    mad_frame = pd.concat(
        [
            _transfer_sample(60, 0, ended=False),
            _transfer_sample(60, 1000, ended=True),
        ],
        ignore_index=True,
    )
    asset = SDNCAMPUS_ASSETS["dropbox"]
    rows = summarize_transfer_file(mad_frame, asset, seed=7, bootstrap_replicates=10)
    halves = {(r["split_half"], r["connection_end"]) for r in rows}
    assert halves == {
        ("estimation", "fin_rst"),
        ("estimation", "censored"),
        ("held_out", "fin_rst"),
        ("held_out", "censored"),
    }
    by_key = {(r["split_half"], r["connection_end"]): r for r in rows}
    assert by_key[("estimation", "censored")]["transfer_rows"] > 5
    assert np.isfinite(by_key[("held_out", "fin_rst")]["transfer_bytes_median"])


def test_transfer_summary_rejects_missing_columns():
    with pytest.raises(ValueError, match="missing columns"):
        summarize_transfer_file(
            pd.DataFrame({"Flow ID": ["x"]}),
            SDNCAMPUS_ASSETS["voip"],
            seed=1,
            bootstrap_replicates=5,
        )
