"""Held-out transfer-level summaries for audited SDNCampus v1 files.

Scope (owner decision 7, 2026-11-10): the flow-profile extraction proved
per-continuation rate and duration. This script adds transfer-level
summaries with a deterministic held-out split and explicit connection-end
classification, without inventing session semantics:

- A record is classified ``fin_rst`` when FIN or RST flag counts are
  positive (tardown observed) and ``censored`` otherwise (timeout or
  capture-window censoring).
- A deterministic record-hash parity split (seeded) separates the
  estimation half from the held-out half. Bootstrap intervals are
  computed on the estimation half only; the held-out half is reported
  as an independent replication check.
- The unit of analysis is one flow continuation (burst), not a user
  session; per-application isolation still applies. These outputs must
  not be presented as session durations, session arrivals or complete
  object sizes beyond the FIN-censored classification limitations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.extract_sdncampus_distributions import (
    SDNCAMPUS_ASSETS,
    DATASET_DOI,
    PAPER_DOI,
    SourceAsset,
    bootstrap_median_ci,
    ensure_asset,
    sha256_file,
)

TRANSFER_COLUMNS = {
    "Flow Duration",
    "Total Length of Fwd Packet",
    "Total Length of Bwd Packet",
    "FIN Flag Count",
    "RST Flag Count",
}


def record_split_keys(frame: pd.DataFrame) -> pd.Series:
    """Salt-able keys from each record's own measures plus its position.

    The audited SDNCampus CSV release carries no flow identity column
    (IPs, ports and IDs are stripped; there are no timestamps either),
    so the record's duration/byte/flag measures plus its row index form
    the key; the index breaks content collisions.
    """

    keys = pd.Series("", index=frame.index, dtype=str)
    for column in TRANSFER_COLUMNS:
        part = pd.to_numeric(frame[column], errors="coerce").fillna(-1)
        keys = keys + part.astype(str) + "|"
    return keys + frame.index.astype(str) + "|"


def heldout_parity(keys: pd.Series, seed: int) -> np.ndarray:
    """Deterministic even/odd split over salted record hashes.

    Returns True for rows in the held-out half.
    """

    def parity(key: object) -> bool:
        digest = hashlib.md5(f"{seed}:{key}".encode("utf-8")).hexdigest()
        return int(digest[:16], 16) % 2 == 1

    return keys.map(parity).to_numpy(dtype=bool)


def classify_flow_end(fin_counts: pd.Series, rst_counts: pd.Series) -> pd.Series:
    fin = pd.to_numeric(fin_counts, errors="coerce").fillna(0.0)
    rst = pd.to_numeric(rst_counts, errors="coerce").fillna(0.0)
    return pd.Series(
        np.where((fin > 0) | (rst > 0), "fin_rst", "censored"),
        index=fin.index,
        dtype=str,
    )


def summarize_transfer_group(
    frame: pd.DataFrame,
    mask: np.ndarray,
    *,
    bootstrap_replicates: int,
    rng: np.random.Generator,
) -> dict[str, float | int]:
    """Summarize one half of the split for one connection-end class."""

    bytes_total = (
        pd.to_numeric(frame["Total Length of Fwd Packet"], errors="coerce").fillna(0.0)
        + pd.to_numeric(frame["Total Length of Bwd Packet"], errors="coerce").fillna(0.0)
    )
    duration_s = pd.to_numeric(frame["Flow Duration"], errors="coerce") / 1e6
    values = bytes_total[mask].to_numpy(dtype=float)
    positive = duration_s[mask].to_numpy(dtype=float) > 0
    low, high = bootstrap_median_ci(values, replicates=bootstrap_replicates, rng=rng)
    return {
        "transfer_rows": int(mask.sum()),
        "transfer_bytes_median": float(np.median(values)) if values.size else float("nan"),
        "transfer_bytes_median_ci_low": low,
        "transfer_bytes_median_ci_high": high,
        "transfer_bytes_p95": float(np.percentile(values, 95)) if values.size else float("nan"),
        "transfer_positive_duration_rows": int(positive.sum()),
        "transfer_duration_median_s": float(np.nanmedian(duration_s[mask]))
        if positive.any()
        else float("nan"),
    }


def summarize_transfer_file(
    frame: pd.DataFrame,
    asset: SourceAsset,
    *,
    seed: int,
    bootstrap_replicates: int,
) -> list[dict[str, object]]:
    missing = TRANSFER_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"{asset.file_name} missing columns: {sorted(missing)}")

    held_out = heldout_parity(record_split_keys(frame), seed)
    end_class = classify_flow_end(frame["FIN Flag Count"], frame["RST Flag Count"])

    rows = []
    for half_name, half_mask in (("estimation", ~held_out), ("held_out", held_out)):
        for end_name in ("fin_rst", "censored"):
            mask = half_mask & end_class.eq(end_name).to_numpy()
            group = summarize_transfer_group(
                frame,
                mask,
                bootstrap_replicates=bootstrap_replicates,
                rng=np.random.default_rng(seed),
            )
            rows.append(
                {
                    "dataset": "SDNCampus",
                    "release_doi": DATASET_DOI,
                    "paper_doi": PAPER_DOI,
                    "application": asset.app,
                    "application_class": asset.class_name,
                    "source_file": asset.file_name,
                    "source_sha256": asset.sha256,
                    "split_half": half_name,
                    "connection_end": end_name,
                    **group,
                }
            )
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apps",
        nargs="+",
        choices=sorted(SDNCAMPUS_ASSETS),
        default=sorted(SDNCAMPUS_ASSETS),
    )
    parser.add_argument("--cache-dir", type=Path, default=Path("data/raw/sdncampus-v1"))
    parser.add_argument(
        "--out", type=Path, default=Path("analysis/sdncampus_transfer_summaries.csv")
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("analysis/sdncampus_transfer_summaries.manifest.json"),
    )
    parser.add_argument("--bootstrap", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261110)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for app in args.apps:
        asset = SDNCAMPUS_ASSETS[app]
        path = ensure_asset(asset, args.cache_dir)
        frame = pd.read_csv(path, low_memory=False)
        half_rows = summarize_transfer_file(
            frame,
            asset,
            seed=args.seed,
            bootstrap_replicates=args.bootstrap,
        )
        rows.extend(half_rows)
        for r in half_rows:
            print(
                f"{app:>12s}/{r['split_half']}/{r['connection_end']}: "
                f"median {r['transfer_bytes_median']} B "
                f"ci [{r['transfer_bytes_median_ci_low']}, "
                f"{r['transfer_bytes_median_ci_high']}]",
            )

    out_frame = pd.DataFrame(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_frame.to_csv(args.out, index=False)
    args.manifest.write_text(
        json.dumps(
            {
                "generated_utc": datetime.now(UTC).isoformat(),
                "dataset_doi": DATASET_DOI,
                "paper_doi": PAPER_DOI,
                "seed": args.seed,
                "bootstrap_replicates": args.bootstrap,
                "split": "md5 parity over salted record content plus row index; "
                "estimation half produces intervals, held-out half reported "
                "for replication; source has no flow identity column",
                "unit_of_analysis": "flow continuation burst; not a session",
                "source_files": {
                    app: {"sha256": SDNCAMPUS_ASSETS[app].sha256}
                    for app in args.apps
                },
                "local_cache_sha256": {
                    asset.file_name: sha256_file(args.cache_dir / asset.file_name)
                    for app in args.apps
                    if (asset := SDNCAMPUS_ASSETS[app])
                },
                "limitations": [
                    "each application ran in isolation; no mixed concurrency",
                    "no device/user identity; session arrivals remain unavailable",
                    "censored records are truncated transfers by construction",
                    "per-application scopes recorded in connection_end classes",
                ],
                "output": str(args.out),
                "rows": len(rows),
            },
            indent=2,
        )
    )
    print(f"wrote {len(rows)} rows to {args.out} and {args.manifest}")


if __name__ == "__main__":
    main()
