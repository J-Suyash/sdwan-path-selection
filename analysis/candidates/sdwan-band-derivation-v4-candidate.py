#!/usr/bin/env python3
"""UNREVIEWED CANDIDATE - NOT APPLIED, NOT INSTALLED IN ANY GATE.

Candidate cross-engine band derivation, v4. Written offline 2026-11-18 against
known branch revision 127c33d. NOT YET RUN against the repository: the offline
`--selftest` (stdlib only, no repo, no data) validates ONLY the math, filters
and parsers added by this script. Repo integration (imports, column names,
grouping behavior, regression checks against committed artifacts) is
UNVALIDATED until the script is executed in the recovery worktree next session.

When run in the worktree it:
- Imports the repo's own scripts/build_switch_calibration.py at runtime
  (importlib by path), so grouping keys, bucket edges and bucketing stay
  repo-owned. This script adds band math and the occupancy recompute only.
- Computes BOTH candidate statistics for all six bandable metrics
  (interruption_s, loss_frac, reordering_frac; plus the three missing rows
  delay_median_ms, jitter_mean_ms, throughput_mbps) over the committed
  48-cell, 238-run calibration pool (cal_v1_full + cal_v2_perpath raw CSVs).
- Statistics: half-range q90 (matches the committed CSV values; the legacy
  column name max_dev_from_median_q90 is a mislabel) and true
  max |replicate - cell median| q90. q90 is a cross-cell quantile, NOT a
  worst-case bound. Which statistic bounds acceptance is an owner decision;
  this script reports both and adopts neither.
- Two occupancy variants, both visible in one artifact:
    original  : recorded queue_occupancy_frac column as-is (contains the
                e11-r00 parse defect).
    repaired  : pipeline-faithful recompute per run from
                testbed/outputs/<round>/<run_id>/qdisc_before.txt with the
                tc-suffix-aware parse (K/M/G 1024-based; suffix prints only
                within +/-15 B of a unit multiple per iproute2
                lib/json_print_math.c sprint_size, public main; installed
                version match not proven) and the SAME denominator the
                pipeline used per round (v1: shared 1000 pkts x 1500 B legacy
                formula; v2: per-path limit x workload packet_bytes), capped
                at 1.0, then re-bucketed with the repo's current
                include_lowest bucketing. This is the 28a58b5 repair
                generalized across all 240 runs, not the owner-pending v1/v2
                harmonization.
- queue_delay_ms is NOT derived: the runner records no such field. Retained
  per-run packet/qdisc evidence permits investigating an estimate, but pure
  queue identification is not automatic; that needs a measurement definition
  before any band can exist.

Owner decisions this script does NOT make: band statistic choice, e00-r00
outlier ruling (both e00 variants reported), v1/v2 occupancy harmonization,
candidate acceptance.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import re
import sys
from pathlib import Path

SWITCH_METRICS = ("interruption_s", "loss_frac", "reordering_frac")
EXTRA_METRICS = ("delay_median_ms", "jitter_mean_ms", "throughput_mbps")
ALL_METRICS = SWITCH_METRICS + EXTRA_METRICS
MIN_REPEATS = 3           # build_switch_calibration.build_rows(min_repeats=3)
STALL_TRIM_FRAC = 0.2     # matches build_rows stall-trim used by prior candidates

# Round-faithful occupancy denominators (committed manifests):
# v1 shared_1000pkt with the legacy 1500 B packet assumption;
# v2 per-path packet limits with the workload's actual packet_bytes.
V1_SHARED_LIMIT_PKTS = 1000
V1_LEGACY_PACKET_BYTES = 1500
V2_PER_PATH_LIMITS = {"bb": 4166, "five_g": 3125, "leo": 2083}

OCC_EDGES = [0.0, 0.05, 0.3, 0.8, 1.0001]
OCC_LABELS = ("empty", "low", "high", "full")

TC_MULT = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}


def quantile(values, q):
    """Linear-interpolation quantile, matching numpy's default method."""
    xs = sorted(float(v) for v in values)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def half_range(mn, mx):
    return max(float(mx) - float(mn), 0.0) / 2.0


def true_max_dev(replicates):
    xs = [float(v) for v in replicates if v is not None
          and not (isinstance(v, float) and math.isnan(v))]
    if len(xs) < 2:
        return None
    srt = sorted(xs)
    n = len(srt)
    med = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0
    return max(abs(v - med) for v in xs)


def stall_trim(sent_frames):
    """Keep runs within +/-20% of the median sent_frames (build_rows rule)."""
    vals = [float(v) for v in sent_frames if v is not None
            and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return [True] * len(sent_frames)
    srt = sorted(vals)
    n = len(srt)
    nominal = srt[n // 2] if n % 2 else (srt[n // 2 - 1] + srt[n // 2]) / 2.0
    out = []
    for v in sent_frames:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(True)  # absent sent_frames: no trim basis
        else:
            out.append(abs(float(v) - nominal) <= STALL_TRIM_FRAC * max(nominal, 1.0))
    return out


def parse_backlog_tc(text):
    """tc-suffix-aware backlog parse (28a58b5 semantics): K/M/G are 1024-based.
    A suffixed print lies within +/-15 B of a unit multiple (iproute2
    sprint_size, public main; installed-version match not proven)."""
    vals = [int(float(num) * TC_MULT[suf])
            for num, suf in re.findall(r"backlog\s+(\d+(?:\.\d+)?)([KMG]?)b", text)]
    return max(vals) if vals else None


def repaired_occupancy(backlog_bytes, round_name, old_path, packet_bytes):
    """Pipeline-faithful denominator per round; capped at 1.0; None if unknown."""
    if backlog_bytes is None or packet_bytes is None:
        return None
    if round_name == "cal_v1_full":
        denom = V1_SHARED_LIMIT_PKTS * V1_LEGACY_PACKET_BYTES
    elif round_name == "cal_v2_perpath":
        limit = V2_PER_PATH_LIMITS.get(old_path)
        if limit is None:
            return None
        denom = limit * packet_bytes
    else:
        return None
    if denom <= 0:
        return None
    return min(backlog_bytes / denom, 1.0)


def reference_bucket(occ):
    """Offline reference reimplementation of pd.cut(right=True,
    include_lowest=True) over OCC_EDGES for self-test only. Repo runs use the
    repo's bucket_values; this exists so the self-test can pin edge semantics:
    first bin is [0.0, 0.05], later bins are left-open."""
    if occ is None or (isinstance(occ, float) and math.isnan(occ)):
        return None
    if occ < OCC_EDGES[0] or occ > OCC_EDGES[-1]:
        return None
    for i, (lo, hi) in enumerate(zip(OCC_EDGES[:-1], OCC_EDGES[1:])):
        if i == 0:
            if lo <= occ <= hi:
                return OCC_LABELS[i]
        elif lo < occ <= hi:
            return OCC_LABELS[i]
    return None


def cell_bands(cells):
    """cells: list of per-cell dicts {metric: [replicate values]} post-filter.
    Returns both statistics per metric, q90 across cells."""
    per_metric_half = {m: [] for m in ALL_METRICS}
    per_metric_maxdev = {m: [] for m in ALL_METRICS}
    for cell in cells:
        for m in ALL_METRICS:
            vals = [v for v in (cell.get(m) or []) if v is not None]
            if len(vals) < 2:
                continue
            per_metric_half[m].append(half_range(min(vals), max(vals)))
            md = true_max_dev(vals)
            if md is not None:
                per_metric_maxdev[m].append(md)
    return {
        "cells_used": len(cells),
        "half_range_q90": {m: quantile(v, 0.9) for m, v in per_metric_half.items()},
        "true_max_dev_from_median_q90": {m: quantile(v, 0.9) for m, v in per_metric_maxdev.items()},
        "n_cells_with_values_half": {m: len(v) for m, v in per_metric_half.items()},
        "n_cells_with_values_maxdev": {m: len(v) for m, v in per_metric_maxdev.items()},
    }


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strict_json(obj):
    return json.dumps(obj, indent=2, allow_nan=False)


def selftest():
    assert abs(quantile([1, 2, 3, 4], 0.9) - 3.7) < 1e-12
    assert quantile([5], 0.9) == 5.0
    assert quantile([], 0.9) is None
    # plan's skewed-cell example: [0,0,0,0,10] -> half-range 5, max-dev 10
    skew = [0, 0, 0, 0, 10]
    assert half_range(min(skew), max(skew)) == 5.0
    assert true_max_dev(skew) == 10.0
    assert true_max_dev([1, 3]) == 1.0
    keep = stall_trim([1000, 1000, 1000, 10000])
    assert keep == [True, True, True, False], keep
    keep = stall_trim([None, 1000, 1000, 1000])
    assert keep == [True, True, True, True], keep
    # tc parse
    assert parse_backlog_tc("qdisc netem backlog 241Kb 163p") == 241 * 1024
    assert parse_backlog_tc("backlog 100b backlog 94Kb") == 94 * 1024
    assert parse_backlog_tc("no backlog here") is None
    # repaired occupancy: v1 e11-r00 case = 241*1024 / (1000*1500) = 0.16452..
    occ = repaired_occupancy(241 * 1024, "cal_v1_full", "bb", 240)
    assert abs(occ - 241 * 1024 / 1_500_000) < 1e-15, occ
    # v1 denominator ignores the workload packet size (legacy formula)
    assert repaired_occupancy(241 * 1024, "cal_v1_full", "bb", 240) == \
           repaired_occupancy(241 * 1024, "cal_v1_full", "bb", 1400)
    # v2 uses per-path limit x actual packet size, capped at 1.0
    assert repaired_occupancy(4166 * 240, "cal_v2_perpath", "bb", 240) == 1.0
    assert repaired_occupancy(2083 * 120, "cal_v2_perpath", "leo", 240) == 0.5
    assert repaired_occupancy(None, "cal_v1_full", "bb", 240) is None
    assert repaired_occupancy(100, "cal_v2_perpath", "unknown_path", 240) is None
    # reference bucketer pins include_lowest edge semantics
    assert reference_bucket(0.0) == "empty"        # zero lands IN first bin
    assert reference_bucket(0.05) == "empty"       # right-closed first bin
    assert reference_bucket(0.0500001) == "low"
    assert reference_bucket(1.0) == "full"
    assert reference_bucket(1.0002) is None
    assert reference_bucket(None) is None
    # cell_bands end-to-end
    cells = [
        {"interruption_s": [0.1, 0.2, 0.3], "delay_median_ms": [10.0, 11.0, 12.0]},
        {"interruption_s": [0.1, 0.5], "delay_median_ms": [10.0, 20.0]},
        {"interruption_s": [0.9], "delay_median_ms": [1.0]},
    ]
    bands = cell_bands(cells)
    assert bands["cells_used"] == 3
    assert abs(bands["half_range_q90"]["interruption_s"] - 0.19) < 1e-12
    assert abs(bands["half_range_q90"]["delay_median_ms"] - 4.6) < 1e-12
    assert bands["half_range_q90"]["loss_frac"] is None
    strict_json(bands)
    try:
        strict_json({"x": float("nan")})
        raise SystemExit("strict_json accepted NaN")
    except ValueError:
        pass
    print("SELFTEST PASSED (offline only: added math, filters, parsers, "
          "reference bucketer. Repo integration remains UNVALIDATED.)")


def load_harmonized_occupancy(repo, rounds):
    """(round, run_id) -> pipeline-faithful repaired occupancy, using the
    per-run join pattern from this session's occupancy evidence script:
    metrics.json gives workload/old_path; the round scenario gives
    packet_bytes; qdisc_before.txt gives the backlog."""
    occ = {}
    for rnd in rounds:
        rdir = repo / "testbed" / "outputs" / rnd
        if not rdir.is_dir():
            continue
        for run_dir in sorted(rdir.iterdir()):
            mpath = run_dir / "metrics.json"
            qpath = run_dir / "qdisc_before.txt"
            if not mpath.is_file() or not qpath.is_file():
                continue
            m = json.loads(mpath.read_text())
            backlog = parse_backlog_tc(qpath.read_text())
            pkt = m.get("packet_bytes")
            if pkt is None:
                # metrics.json may omit packet_bytes; fall back to scenario
                pkt = _scenario_packet_bytes(repo, m)
            occ[(rnd, str(m.get("run_id", run_dir.name)))] = repaired_occupancy(
                backlog, rnd, m.get("old_path"), pkt)
    return occ


def _scenario_packet_bytes(repo, metrics):
    scen = metrics.get("scenario")
    wl = metrics.get("workload")
    if not scen or not wl:
        return None
    for cand in sorted((repo / "testbed" / "scenarios").glob("*.json")):
        try:
            raw = json.loads(cand.read_text())
        except Exception:
            continue
        if isinstance(raw, dict) and raw.get("name") == scen and "workloads" in raw:
            spec = raw["workloads"].get(wl)
            if isinstance(spec, dict) and "packet_bytes" in spec:
                return int(spec["packet_bytes"])
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true",
                    help="offline self-test of added math/parsers only (no repo)")
    ap.add_argument("--repo", default="/home/sxtr/Projects/Major Project-instinct-recovery")
    ap.add_argument("--out", default="/tmp/sdwan-band-derivation-v4-candidate.json")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return

    repo = Path(args.repo)
    spec = importlib.util.spec_from_file_location(
        "bsc", repo / "scripts" / "build_switch_calibration.py")
    bsc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bsc)

    rounds = ["cal_v1_full", "cal_v2_perpath"]
    raw_paths = {rnd: repo / "testbed" / "outputs" / rnd / "switch_metrics_raw.csv"
                 for rnd in rounds}

    def collect(occ_override):
        """Group raw rows into cells. occ_override: None = recorded column;
        else dict (round, run_id) -> repaired occupancy replacing the column
        before repo bucketing."""
        cells = []
        for rnd, rp in raw_paths.items():
            raw = bsc.read_raw(rp)
            if occ_override is not None:
                raw = raw.copy()
                raw["queue_occupancy_frac"] = [
                    occ_override.get((rnd, str(rid)), recorded)
                    for rid, recorded in zip(raw["run_id"].tolist(),
                                             raw["queue_occupancy_frac"].tolist())
                ]
            framed = bsc.with_buckets(raw)  # repo-owned bucketing incl. include_lowest
            grouped = framed.groupby(list(bsc.KEY_COLUMNS), dropna=False)
            for _key, group in grouped:
                if len(group) < MIN_REPEATS:
                    continue
                if "sent_frames" in group.columns:
                    keep = stall_trim(group["sent_frames"].tolist())
                    group = group[keep]
                if len(group) < 2:
                    continue
                cell = {}
                for m in ALL_METRICS:
                    if m in group.columns:
                        cell[m] = [None if (isinstance(v, float) and math.isnan(v)) else float(v)
                                   for v in group[m].tolist()]
                cells.append(cell)
        return cells

    original = cell_bands(collect(None))
    repaired_occ = load_harmonized_occupancy(repo, rounds)
    repaired = cell_bands(collect(repaired_occ))

    result = {
        "status": "UNREVIEWED CANDIDATE EVIDENCE - not installed in any gate",
        "revision_authored_against": "127c33d (instinct/reproducibility-diagnostics)",
        "integration_validated": False,
        "inputs": {rnd: {"path": str(rp), "sha256": sha256(rp)}
                   for rnd, rp in raw_paths.items()},
        "min_repeats": MIN_REPEATS,
        "stall_trim_frac": STALL_TRIM_FRAC,
        "q90_note": "q90 is a cross-cell quantile, not a worst-case bound",
        "queue_delay_ms": "not derivable: runner records no queue_delay_ms field",
        "original_pipeline": original,
        "repaired_pipeline": {
            "definition": "suffix-aware qdisc parse + pipeline-faithful denominators "
                          "(v1 shared 1000x1500; v2 per-path x packet_bytes), capped 1.0, "
                          "repo include_lowest bucketing",
            "n_runs_recomputed": len(repaired_occ),
            "bands": repaired,
        },
        "regression_checks": {
            "original_cells_48": original["cells_used"] == 48,
            "repaired_cells_present": repaired["cells_used"] > 0,
        },
    }
    Path(args.out).write_text(strict_json(result))
    print(strict_json({"wrote": args.out,
                       "original_cells": original["cells_used"],
                       "repaired_cells": repaired["cells_used"],
                       "runs_recomputed": len(repaired_occ)}))


if __name__ == "__main__":
    main()
