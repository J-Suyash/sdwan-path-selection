"""Extract flow-level distributions from audited SDNCampus v1 CSV files.

The source runs each application in isolation. Results therefore describe
per-application flow behaviour and must not be used as evidence of natural
mixed-application concurrency in an enterprise branch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATASET_DOI = "10.17632/wvp9tksn72.1"
DATASET_URL = "https://data.mendeley.com/datasets/wvp9tksn72/1"
PAPER_DOI = "10.56279/jicts.v4i1.422"

REQUIRED_COLUMNS = {
    "Flow Duration",
    "Total Length of Fwd Packet",
    "Total Length of Bwd Packet",
    "Total Fwd Packet",
    "Total Bwd packets",
}


@dataclass(frozen=True)
class SourceAsset:
    app: str
    class_name: str
    file_name: str
    file_id: str
    sha256: str
    size_bytes: int

    @property
    def download_url(self) -> str:
        return (
            "https://data.mendeley.com/public-files/datasets/"
            f"wvp9tksn72/files/{self.file_id}/file_downloaded"
        )


SDNCAMPUS_ASSETS = {
    asset.app: asset
    for asset in [
        SourceAsset(
            app="voip",
            class_name="voice",
            file_name="voip.csv",
            file_id="3440bac6-c0cc-4345-a31d-0cd2fe81ede4",
            sha256="04e40b29b084cb8cf3d519c887d54f8b4cafc9368d4d07aeba9ee30fe9521d96",
            size_bytes=50_828_271,
        ),
        SourceAsset(
            app="googlemeet",
            class_name="video",
            file_name="googlemeet.csv",
            file_id="3cfd7a74-c117-4cb7-b0e1-1be72d8ef0c5",
            sha256="0427b5ba814d966022719440a2cfcd54137ab70b826b7903f49cce79adbe5093",
            size_bytes=61_785_103,
        ),
        SourceAsset(
            app="gmail",
            class_name="interactive",
            file_name="gmail.csv",
            file_id="93244208-cef2-485a-91d0-893e3776b8a1",
            sha256="517b67df6b246d9edf03b9fd3c601c88b74f5ccb6783cd677054fb166d0b0819",
            size_bytes=43_077_450,
        ),
        SourceAsset(
            app="dropbox",
            class_name="bulk",
            file_name="dropbox.csv",
            file_id="b6142864-58b9-4295-8e1e-8cfd7c6596e3",
            sha256="749051697f5fbd1bc1b2b62211072190c1be94c9a72b4ad27c23a66d7c44eb00",
            size_bytes=49_797_553,
        ),
    ]
}


def bootstrap_median_ci(
    values: np.ndarray,
    *,
    replicates: int,
    rng: np.random.Generator,
    max_sample_rows: int = 20_000,
) -> tuple[float, float]:
    """Return a deterministic bootstrap interval for a finite median sample."""

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan"), float("nan")
    if finite.size > max_sample_rows:
        finite = rng.choice(finite, size=max_sample_rows, replace=False)
    medians = np.empty(replicates, dtype=float)
    for idx in range(replicates):
        medians[idx] = np.median(rng.choice(finite, size=finite.size, replace=True))
    low, high = np.percentile(medians, [2.5, 97.5])
    return float(low), float(high)


def summarize_flow_frame(
    frame: pd.DataFrame,
    asset: SourceAsset,
    *,
    bootstrap_replicates: int,
    rng: np.random.Generator,
) -> dict[str, float | int | str]:
    """Summarize one application without claiming session-level semantics."""

    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{asset.file_name} missing columns: {sorted(missing)}")

    duration_s = pd.to_numeric(frame["Flow Duration"], errors="coerce") / 1e6
    up_bytes = pd.to_numeric(frame["Total Length of Fwd Packet"], errors="coerce")
    down_bytes = pd.to_numeric(frame["Total Length of Bwd Packet"], errors="coerce")
    total_bytes = up_bytes + down_bytes
    total_packets = pd.to_numeric(
        frame["Total Fwd Packet"], errors="coerce"
    ) + pd.to_numeric(frame["Total Bwd packets"], errors="coerce")
    positive_duration = duration_s > 0
    flow_mbps = (
        total_bytes.where(positive_duration) * 8.0 / duration_s.where(positive_duration)
    ) / 1e6
    downlink_fraction = down_bytes / total_bytes.where(total_bytes > 0)

    duration_values = duration_s.to_numpy(dtype=float)
    flow_mbps_values = flow_mbps.to_numpy(dtype=float)
    duration_ci_low, duration_ci_high = bootstrap_median_ci(
        duration_values, replicates=bootstrap_replicates, rng=rng
    )
    mbps_ci_low, mbps_ci_high = bootstrap_median_ci(
        flow_mbps_values, replicates=bootstrap_replicates, rng=rng
    )

    return {
        "dataset": "SDNCampus",
        "release_doi": DATASET_DOI,
        "paper_doi": PAPER_DOI,
        "application": asset.app,
        "application_class": asset.class_name,
        "source_file": asset.file_name,
        "source_sha256": asset.sha256,
        "source_size_bytes": asset.size_bytes,
        "flow_rows": len(frame),
        "zero_duration_rows": int((duration_s <= 0).sum()),
        "duration_unit": "microseconds in source; converted to seconds",
        "duration_median_s": float(np.nanmedian(duration_values)),
        "duration_median_ci_low_s": duration_ci_low,
        "duration_median_ci_high_s": duration_ci_high,
        "duration_p95_s": float(np.nanpercentile(duration_values, 95)),
        "total_bytes_median": float(np.nanmedian(total_bytes)),
        "total_bytes_p95": float(np.nanpercentile(total_bytes, 95)),
        "total_packets_median": float(np.nanmedian(total_packets)),
        "flow_mbps_median": float(np.nanmedian(flow_mbps_values)),
        "flow_mbps_median_ci_low": mbps_ci_low,
        "flow_mbps_median_ci_high": mbps_ci_high,
        "flow_mbps_p95": float(np.nanpercentile(flow_mbps_values, 95)),
        "downlink_byte_fraction_median": float(
            np.nanmedian(downlink_fraction.to_numpy(dtype=float))
        ),
        "timestamp_semantics": "relative flow durations and IATs; no absolute timestamp",
        "concurrency_semantics": "each application run in isolation; no mixed concurrency",
        "bootstrap_replicates": bootstrap_replicates,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_asset(asset: SourceAsset, cache_dir: Path) -> Path:
    """Download an audited asset once and verify its published SHA-256."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / asset.file_name
    if target.exists():
        if sha256_file(target) != asset.sha256:
            raise ValueError(f"checksum mismatch for cached {target}")
        return target

    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(
        asset.download_url, headers={"User-Agent": "sdwan-project-audit/1.0"}
    )
    digest = hashlib.sha256()
    size = 0
    last_report = 0
    try:
        with urllib.request.urlopen(request) as response, partial.open("wb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
                if size - last_report >= 10 * 1024 * 1024:
                    print(
                        f"{asset.file_name}: {size / 1024**2:.1f} MiB",
                        file=sys.stderr,
                    )
                    last_report = size
        if size != asset.size_bytes:
            raise ValueError(
                f"{asset.file_name}: expected {asset.size_bytes} B, got {size} B"
            )
        if digest.hexdigest() != asset.sha256:
            raise ValueError(f"{asset.file_name}: published SHA-256 mismatch")
        os.replace(partial, target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apps",
        nargs="+",
        choices=sorted(SDNCAMPUS_ASSETS),
        default=sorted(SDNCAMPUS_ASSETS),
        help="Representative SDNCampus applications to summarize.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("data/raw/sdncampus-v1"),
        help="Ignored local download cache.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("analysis/sdncampus_flow_profiles.csv"),
    )
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20261106)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.bootstrap < 1:
        raise ValueError("--bootstrap must be positive")
    rng = np.random.default_rng(args.seed)
    rows = []
    for app in args.apps:
        asset = SDNCAMPUS_ASSETS[app]
        path = ensure_asset(asset, args.cache_dir)
        frame = pd.read_csv(
            path,
            usecols=sorted(REQUIRED_COLUMNS),
            low_memory=False,
        )
        rows.append(
            summarize_flow_frame(
                frame,
                asset,
                bootstrap_replicates=args.bootstrap,
                rng=rng,
            )
        )
        print(
            f"{app}: {len(frame):,} flows, "
            f"median {rows[-1]['duration_median_s']:.3f} s",
            file=sys.stderr,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out, index=False)
    manifest_path = args.out.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(
            {
                "dataset": "SDNCampus",
                "release_doi": DATASET_DOI,
                "dataset_url": DATASET_URL,
                "paper_doi": PAPER_DOI,
                "retrieved": "2026-11-06",
                "cache_dir": str(args.cache_dir),
                "output": str(args.out),
                "bootstrap_replicates": args.bootstrap,
                "bootstrap_sample_limit": 20_000,
                "seed": args.seed,
                "applications": {
                    app: SDNCAMPUS_ASSETS[app].__dict__ for app in args.apps
                },
                "limitations": [
                    "Controlled application runs, not natural mixed concurrency.",
                    "Flow records are not user or application sessions.",
                    "No absolute timestamps are present in the final CSV.",
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.out} and {manifest_path}")


if __name__ == "__main__":
    main()
