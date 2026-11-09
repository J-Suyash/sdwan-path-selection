import numpy as np
import pandas as pd
import pytest

from scripts.extract_sdncampus_distributions import (
    SDNCAMPUS_ASSETS,
    summarize_flow_frame,
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
