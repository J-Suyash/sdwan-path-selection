"""Trace preprocessing pipeline (proposal Section 11.2).

Turns every raw dataset into a uniform per-second Parquet table:

    utc         datetime (UTC, 1 s grid where the source supports it)
    source      wetlinks | raca5g | lumos5g | lens | collected
    site        origin label (site, operator, etc.)
    rtt_ms      mean per-second round-trip time (NaN = not measured)
    jitter_ms   mean absolute difference of consecutive RTTs
    loss_frac   packet-loss fraction in [0, 1] (NaN = not measured)
    dl_mbps     downlink throughput/capacity (NaN = not measured)
    ul_mbps     uplink throughput/capacity (NaN = not measured)
    outage      True when the previous data point is more than 5 s away
    meta        source-specific extra context

Usage:
    python scripts/preprocess_traces.py all \
        --data-root data/raw --out data/processed
"""

import argparse
import glob
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd


GAP_S = 5.0


def _read_csvs(pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise FileNotFoundError(f"no files match {pattern}")
    return pd.concat([pd.read_csv(f, low_memory=False) for f in files], ignore_index=True)


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("utc").reset_index(drop=True)
    gap = df["utc"].diff().dt.total_seconds()
    df["outage"] = gap > GAP_S
    df.loc[0, "outage"] = False
    for col in ("rtt_ms", "jitter_ms", "loss_frac", "dl_mbps", "ul_mbps"):
        if col in df:
            df[col] = df[col].astype("float32")
    return df


def _jitter_from_rtt(rtt: pd.Series) -> pd.Series:
    return rtt.diff().abs()


def load_wetlinks(root: str) -> pd.DataFrame:
    frames = []
    for csv_path in sorted(glob.glob(os.path.join(root, "Preprocessed_Data", "analysis_data_*.csv"))):
        raw = pd.read_csv(csv_path, low_memory=False)
        raw["start"] = pd.to_datetime(raw["timestamp_start"], errors="coerce")
        raw["end"] = pd.to_datetime(raw["timestamp_end"], errors="coerce")
        raw = raw.dropna(subset=["start", "end"])
        rows = []
        for _, r in raw.iterrows():
            span = max(int((r["end"] - r["start"]).total_seconds()), 1)
            for i in range(span):
                rows.append(
                    {
                        "utc": r["start"] + pd.Timedelta(seconds=i),
                        "source": "wetlinks",
                        "site": r["site_name"],
                        "rtt_ms": r.get("ping_avg"),
                        "loss_frac": (r.get("ping_packet_loss") or 0) / 100.0,
                        "dl_mbps": r.get("download", np.nan) / 1e6,
                        "ul_mbps": r.get("upload", np.nan) / 1e6,
                        "meta": f"server={r.get('server')}",
                    }
                )
        frames.append(pd.DataFrame(rows))
    df = pd.concat(frames, ignore_index=True)
    df = df.groupby(["utc", "source", "site", "meta"], as_index=False).agg(
        rtt_ms=("rtt_ms", "mean"),
        loss_frac=("loss_frac", "mean"),
        dl_mbps=("dl_mbps", "mean"),
        ul_mbps=("ul_mbps", "mean"),
    )
    df["jitter_ms"] = df.groupby(["site"])["rtt_ms"].transform(_jitter_from_rtt)
    return _finalize(df)


def load_raca5g(root: str) -> pd.DataFrame:
    pattern = os.path.join(root, "**", "*.csv")
    df = _read_csvs(pattern)
    df["utc"] = pd.to_datetime(df["Timestamp"], format="%Y.%m.%d_%H.%M.%S")
    out = pd.DataFrame(
        {
            "utc": df["utc"],
            "source": "raca5g",
            "site": df["Operatorname"].fillna("unknown"),
            "rtt_ms": pd.to_numeric(df["PINGAVG"], errors="coerce"),
            "loss_frac": pd.to_numeric(df["PINGLOSS"], errors="coerce") / 100.0,
            "dl_mbps": pd.to_numeric(df["DL_bitrate"], errors="coerce") / 1e3,
            "ul_mbps": pd.to_numeric(df["UL_bitrate"], errors="coerce") / 1e3,
            "meta": df["NetworkMode"].fillna("") + "/" + df["State"].fillna(""),
        }
    )
    out["jitter_ms"] = out.groupby("site")["rtt_ms"].transform(_jitter_from_rtt)
    return _finalize(out)


def load_lumos5g(root: str) -> pd.DataFrame:
    csv_path = glob.glob(os.path.join(root, "**", "Lumos5G-v1.0.csv"), recursive=True)[0]
    raw = pd.read_csv(csv_path, low_memory=False)
    # No absolute timestamps in Lumos5G; build a synthetic clock that
    # stacks runs sequentially (documented limitation, fine for replay).
    base = datetime(2020, 1, 1, tzinfo=timezone.utc)
    offsets = raw.groupby("run_num")["seq_num"].max().cumsum().shift(fill_value=0)
    raw["t"] = raw["run_num"].map(offsets) + raw["seq_num"]
    out = pd.DataFrame(
        {
            "utc": base + pd.to_timedelta(raw["t"], unit="s"),
            "source": "lumos5g",
            "site": f"tower_{raw['tower_id']}",
            "rtt_ms": np.nan,
            "loss_frac": np.nan,
            "dl_mbps": pd.to_numeric(raw["Throughput"], errors="coerce"),
            "ul_mbps": np.nan,
            "meta": raw["mobility_mode"].fillna("") + "/run_" + raw["run_num"].astype(str),
        }
    )
    return _finalize(out)


def load_lens(root: str) -> pd.DataFrame:
    pattern = os.path.join(root, "**", "*.csv")
    df = _read_csvs(pattern)
    ts = pd.to_numeric(df["timestamp"], errors="coerce")
    # LENS processed CSVs use either nanoseconds or seconds since epoch.
    unit = "ns" if (ts.dropna() > 1e16).any() else "s"
    df["utc"] = pd.to_datetime(ts, unit=unit, utc=True)
    rtt = pd.to_numeric(df["rtt"], errors="coerce").clip(lower=0)
    loss = rtt.isna() | (rtt <= 0)
    out = pd.DataFrame(
        {
            "utc": df["utc"],
            "source": "lens",
            "site": "starlink",
            "rtt_ms": rtt.where(~loss),
            "loss_frac": loss.astype(float),
            "dl_mbps": np.nan,
            "ul_mbps": np.nan,
            "meta": "",
        }
    )
    out["jitter_ms"] = out["rtt_ms"].transform(_jitter_from_rtt)
    return _finalize(out)


def load_collected(root: str) -> pd.DataFrame:
    frames = []
    for csv_path in sorted(glob.glob(os.path.join(root, "**", "*.csv"), recursive=True)):
        raw = pd.read_csv(csv_path, low_memory=False)
        pings = raw[raw["kind"] == "ping"].copy()
        if pings.empty:
            continue
        pings["utc"] = pd.to_datetime(pings["ts_epoch_ms"], unit="ms", utc=True)
        per_sec = (
            pings.groupby(["label", pings["utc"].dt.floor("s")])
            .agg(rtt_ms=("rtt_ms", "mean"), count=("rtt_ms", "count"))
            .reset_index()
            .rename(columns={"utc": "utc"})
        )
        expected = max(round(per_sec["count"].median()), 1)
        per_sec["loss_frac"] = (1 - per_sec["count"] / expected).clip(lower=0, upper=1)
        per_sec["jitter_ms"] = per_sec.groupby("label")["rtt_ms"].transform(
            _jitter_from_rtt
        )
        per_sec["source"] = "collected"
        per_sec["dl_mbps"] = np.nan
        per_sec["ul_mbps"] = np.nan
        per_sec["meta"] = ""
        frames.append(
            per_sec.rename(columns={"label": "site"})[
                ["utc", "source", "site", "rtt_ms", "jitter_ms", "loss_frac",
                 "dl_mbps", "ul_mbps", "meta"]
            ]
        )
    return _finalize(pd.concat(frames, ignore_index=True))


LOADERS = {
    "wetlinks": load_wetlinks,
    "raca5g": load_raca5g,
    "lumos5g": load_lumos5g,
    "lens": load_lens,
    "collected": load_collected,
}

# Directory name inside data/raw/ for each source (case-sensitive on disk).
RAW_DIRS = {
    "wetlinks": "WetLinks",
    "raca5g": "raca5g",
    "lumos5g": "lumos5g",
    "lens": "LENS",
    "collected": "collected",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+", choices=list(LOADERS) + ["all"])
    ap.add_argument("--data-root", default="data/raw")
    ap.add_argument("--out", default="data/processed")
    args = ap.parse_args()

    sources = list(LOADERS) if args.sources == ["all"] else args.sources
    os.makedirs(args.out, exist_ok=True)
    for name in sources:
        src_root = os.path.join(args.data_root, RAW_DIRS[name])
        if not os.path.isdir(src_root):
            print(f"[skip] {name}: no raw directory at {src_root}")
            continue
        try:
            df = LOADERS[name](src_root)
        except FileNotFoundError as exc:
            print(f"[skip] {name}: {exc}")
            continue
        out_path = os.path.join(args.out, f"{name}.parquet")
        df.to_parquet(out_path, index=False)
        span_h = (df["utc"].max() - df["utc"].min()).total_seconds() / 3600
        print(
            f"[ok] {name}: {len(df)} rows, {span_h:.1f} h span -> {out_path}"
        )
        meta = {
            "source": name,
            "rows": len(df),
            "utc_min": df["utc"].min().isoformat(),
            "utc_max": df["utc"].max().isoformat(),
            "created": datetime.now(timezone.utc).isoformat(),
        }
        with open(out_path + ".meta.json", "w") as fh:
            json.dump(meta, fh, indent=2)


if __name__ == "__main__":
    main()
