"""Trace loading for the emulator: turn processed Parquet files into
per-second series for an episode (proposal Sections 10.1, 11.1)."""

from pathlib import Path

import numpy as np
import pandas as pd


def load_source_df(data_root: str, source: str) -> pd.DataFrame:
    path = Path(data_root) / f"{source}.parquet"
    return pd.read_parquet(path)


def _fill_nan(arr: np.ndarray, fallback: float) -> np.ndarray:
    out = arr.astype(float).copy()
    mask = np.isnan(out)
    if mask.all():
        out[:] = fallback
    else:
        idx = np.arange(len(out))
        out[mask] = np.interp(idx[mask], idx[~mask], out[~mask])
    return out


def build_series(
    df: pd.DataFrame | None,
    steps: int,
    rng: np.random.Generator,
    fallback_rtt_ms: float,
    cap_mbps: float,
    step_s: float = 1.0,
) -> dict[str, np.ndarray]:
    """Sample a contiguous episode window; tile if the source is short."""
    if df is None:
        return synthetic_series(steps, rng, fallback_rtt_ms, cap_mbps)
    df = df.dropna(subset=["utc"]).sort_values("utc").reset_index(drop=True)
    if len(df) == 0:
        return synthetic_series(steps, rng, fallback_rtt_ms, cap_mbps)

    t_min = df["utc"].min()
    t_max = df["utc"].max()
    dur = pd.Timedelta(seconds=steps * step_s)
    if t_max - t_min >= dur:
        max_offset = int((t_max - t_min - dur).total_seconds()) + 1
        start_t = t_min + pd.Timedelta(seconds=float(rng.integers(0, max_offset)))
    else:
        start_t = t_min
    window = df[(df["utc"] >= start_t) & (df["utc"] < start_t + dur)]
    if window.empty:
        return synthetic_series(steps, rng, fallback_rtt_ms, cap_mbps)

    offsets = np.arange(steps, dtype=float) * step_s
    grid = start_t.floor("s") + pd.to_timedelta(offsets, unit="s")

    def reindex(col: str) -> pd.Series:
        idx = window["utc"].dt.floor("s")
        s = window.set_index(idx)[col]
        return s[~s.index.duplicated()].reindex(grid)

    rtt = _fill_nan(reindex("rtt_ms").to_numpy(), fallback_rtt_ms)
    loss = _fill_nan(reindex("loss_frac").to_numpy(), 0.0)
    dl = np.nan_to_num(reindex("dl_mbps").to_numpy(), nan=0.0)
    outage = reindex("outage").fillna(False).to_numpy(dtype=bool)

    capacity = np.minimum(np.maximum(dl, cap_mbps * 0.2), cap_mbps)
    capacity[outage] = 0.0
    return {
        "rtt_ms": rtt,
        "loss": np.clip(loss, 0, 1),
        "capacity": capacity,
        "up": ~outage,
    }


def synthetic_series(
    steps: int, rng: np.random.Generator, fallback_rtt_ms: float, cap_mbps: float
) -> dict[str, np.ndarray]:
    """Smooth random-walk series used when no trace file exists."""
    rtt = np.clip(
        np.full(steps, fallback_rtt_ms) + np.cumsum(rng.normal(0, 1.5, steps)),
        5,
        500,
    )
    loss = np.clip(rng.normal(0.002, 0.003, steps), 0, 0.05)
    capacity = np.full(steps, cap_mbps * rng.uniform(0.6, 1.0))
    return {
        "rtt_ms": rtt,
        "loss": loss,
        "capacity": capacity,
        "up": np.ones(steps, dtype=bool),
    }
