import numpy as np
import pandas as pd

from scripts.build_switch_calibration import (
    build_rows,
    coefficient_of_variation,
    with_buckets,
)


def _raw_frame(reps: int, key_suffix: str = "") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "run_id": [f"e00-r{r:02d}" for r in range(reps)],
            "old_rtt_ms": np.full(reps, 187.4),
            "new_rtt_ms": np.full(reps, 75.0),
            "old_jitter_ms": np.full(reps, 0.3),
            "new_jitter_ms": np.full(reps, 1.0),
            "flow_type": [f"voice{key_suffix}"] * reps,
            "transport": ["udp"] * reps,
            "packets_in_flight": np.full(reps, 14.0),
            "queue_occupancy_frac": np.full(reps, 0.001),
            "interruption_s": np.array([0.05, 0.07, 0.06])[:reps],
            "loss_frac": np.zeros(reps),
            "reordering_frac": np.zeros(reps),
            "route_update_s": np.full(reps, 0.09),
            "repetition": list(range(reps)),
        }
    )


def test_build_rows_promotes_only_sufficient_repeats():
    frame = with_buckets(
        pd.concat([_raw_frame(3), _raw_frame(2, key_suffix="x")], ignore_index=True)
    )
    rows, _ = build_rows(frame, min_repeats=3)
    assert len(rows) == 2
    usable = rows[rows["quality"] == "usable"]
    assert len(usable) == 1
    assert usable.iloc[0]["interruption_s_mean"] == 0.06


def test_fraction_cv_uses_max_scale_for_near_zero_means():
    values = np.array([0.001, 0.002, 0.0])
    cv = coefficient_of_variation(values)
    assert np.isfinite(cv)
    assert cv > 0


def test_in_flight_bucket_assignment():
    frame = _raw_frame(3)
    bucketed = with_buckets(frame)
    assert (bucketed["in_flight_bucket"] == "large").all()
    assert (bucketed["occupancy_bucket"] == "empty").all()
