"""Data-driven path-switch transient model.

The model intentionally returns no transient penalty until a calibration file
contains measured switching observations. This prevents an unsupported RTT
to loss formula from silently becoming a production assumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "old_rtt_ms",
    "new_rtt_ms",
    "old_jitter_ms",
    "new_jitter_ms",
    "packets_in_flight",
    "flow_type",
    "transport",
    "queue_occupancy_frac",
    "interruption_s",
    "loss_frac",
    "reordering_frac",
}


@dataclass(frozen=True)
class SwitchEffect:
    interruption_s: float = 0.0
    loss_frac: float = 0.0
    reordering_frac: float = 0.0
    calibrated: bool = False
    sample_count: int = 0


class SwitchingModel:
    def __init__(self, calibration_path: str | Path | None = None):
        self.calibration_path = str(calibration_path) if calibration_path else None
        self.samples = pd.DataFrame()
        if calibration_path:
            self.samples = self._load(calibration_path)

    @staticmethod
    def _load(path: str | Path) -> pd.DataFrame:
        frame = pd.read_csv(path)
        missing = REQUIRED_COLUMNS - set(frame.columns)
        if missing:
            raise ValueError(f"switch calibration missing columns: {sorted(missing)}")
        if frame.empty:
            return frame
        numeric = REQUIRED_COLUMNS - {"flow_type", "transport"}
        frame[list(numeric)] = frame[list(numeric)].apply(
            pd.to_numeric, errors="coerce"
        )
        frame = frame.dropna(subset=list(numeric)).copy()
        for col in ("interruption_s", "loss_frac", "reordering_frac"):
            if (frame[col] < 0).any():
                raise ValueError(f"switch calibration contains negative {col}")
        return frame

    def predict(
        self,
        *,
        old_rtt_ms: float,
        new_rtt_ms: float,
        old_jitter_ms: float,
        new_jitter_ms: float,
        packets_in_flight: float,
        flow_type: str,
        transport: str,
        queue_occupancy_frac: float,
    ) -> SwitchEffect:
        if self.samples.empty:
            return SwitchEffect()
        candidates = self.samples[
            (self.samples["flow_type"] == flow_type)
            & (self.samples["transport"] == transport)
        ]
        if candidates.empty:
            candidates = self.samples
        features = np.array(
            [
                old_rtt_ms,
                new_rtt_ms,
                old_jitter_ms,
                new_jitter_ms,
                packets_in_flight,
                queue_occupancy_frac,
            ],
            dtype=float,
        )
        matrix = candidates[
            [
                "old_rtt_ms",
                "new_rtt_ms",
                "old_jitter_ms",
                "new_jitter_ms",
                "packets_in_flight",
                "queue_occupancy_frac",
            ]
        ].to_numpy(float)
        scale = np.maximum(np.nanmedian(np.abs(matrix), axis=0), 1.0)
        idx = int(np.argmin(np.sum(((matrix - features) / scale) ** 2, axis=1)))
        row = candidates.iloc[idx]
        return SwitchEffect(
            interruption_s=float(row["interruption_s"]),
            loss_frac=float(np.clip(row["loss_frac"], 0.0, 1.0)),
            reordering_frac=float(np.clip(row["reordering_frac"], 0.0, 1.0)),
            calibrated=True,
            sample_count=len(candidates),
        )
