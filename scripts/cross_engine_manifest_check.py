#!/usr/bin/env python3
"""Cross-engine case-manifest gap diagnostic (mechanical; no validation).

Reports what the cross-engine case manifest still needs before the existing
Mininet runner (testbed.scenario.load_scenario) could execute its cases.

This tool performs NO scientific validation, constructs NO scenario files,
and writes NO output files. Closing the reported schema gaps requires
owner-reviewed mapping decisions (for example the semantics of
``capacity_floor_frac``), which this diagnostic deliberately does not invent.

Usage:
    python scripts/cross_engine_manifest_check.py [--manifest PATH]
        [--thresholds PATH] [--reference PATH] [--json]

Exit codes:
    0  no gaps: manifest is runner-schema-complete and every requested
       metric has a band row in the thresholds CSV
    1  gaps exist (see report)
    2  unreadable or invalid inputs
"""

import argparse
import csv
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "testbed" / "scenarios" / "cross_engine_cases.json"
DEFAULT_THRESHOLDS = REPO_ROOT / "analysis" / "cross_engine_thresholds.csv"
DEFAULT_REFERENCE = REPO_ROOT / "testbed" / "scenarios" / "switch_calibration_v2.json"

# Runner schema required by testbed.scenario.load_scenario.
RUNNER_TOP_LEVEL = ("server_ip", "paths", "workloads", "events")
RUNNER_PATH_FIELDS = ("capacity_mbps", "one_way_delay_ms", "jitter_ms", "loss_pct")
RUNNER_WORKLOAD_FIELDS = (
    "flow_type", "transport", "client_ip", "server_port",
    "rate_mbps", "duration_s", "warmup_s", "packet_bytes",
)

BAND_COLUMN_CANDIDATES = ("cell_half_range_q90", "max_dev_from_median_q90")

DISCLAIMER = (
    "This report performs no scientific validation, constructs no scenarios, "
    "and writes no files. Closing schema gaps requires owner-reviewed mapping "
    "decisions; they are not made here."
)


class InputError(Exception):
    """Unreadable or structurally invalid input file."""


def _load_json(path: Path, label: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"{label}: cannot read {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise InputError(f"{label}: invalid JSON in {path}: {exc}") from None
    if not isinstance(data, dict):
        raise InputError(f"{label}: {path} must contain a JSON object")
    return data


def _runner_schema_gaps(manifest: dict) -> list[str]:
    """Which runner-required sections the manifest does not provide."""

    gaps = []
    for section in RUNNER_TOP_LEVEL:
        if section not in manifest:
            gaps.append(f"missing runner section: {section}")
    paths = manifest.get("paths")
    if isinstance(paths, dict):
        for name, spec in paths.items():
            missing = [f for f in RUNNER_PATH_FIELDS if not isinstance(spec, dict) or f not in spec]
            if missing:
                gaps.append(f"path {name!r} missing runner fields: {', '.join(missing)}")
    workloads = manifest.get("workloads")
    if isinstance(workloads, dict):
        for name, spec in workloads.items():
            missing = [f for f in RUNNER_WORKLOAD_FIELDS if not isinstance(spec, dict) or f not in spec]
            if missing:
                gaps.append(f"workload {name!r} missing runner fields: {', '.join(missing)}")
    return gaps


def _case_queue_gaps(manifest: dict) -> tuple[list[str], list[dict]]:
    """Per-case queue-config coverage; returns (gaps, per-case details)."""

    gaps: list[str] = []
    details: list[dict] = []
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        return gaps, details
    queue_config = manifest.get("queue_config")
    per_path = {}
    manifest_packet_bytes = None
    if isinstance(queue_config, dict):
        per_path = queue_config.get("per_path_queue_limit_packets") or {}
        manifest_packet_bytes = queue_config.get("packet_bytes")
    for case in cases:
        if not isinstance(case, dict):
            continue
        case_id = case.get("id", "<unnamed>")
        detail = {"id": case_id, "gaps": []}
        for role in ("old_path", "new_path"):
            path_name = case.get(role)
            if path_name is not None and path_name not in per_path:
                msg = f"case {case_id}: {role} {path_name!r} not covered by queue_config.per_path_queue_limit_packets"
                detail["gaps"].append(msg)
                gaps.append(msg)
        case_packet_bytes = case.get("packet_bytes")
        if (manifest_packet_bytes is not None and case_packet_bytes is not None
                and case_packet_bytes != manifest_packet_bytes):
            msg = (f"case {case_id}: packet_bytes {case_packet_bytes} differs from "
                   f"queue_config.packet_bytes {manifest_packet_bytes}")
            detail["gaps"].append(msg)
            gaps.append(msg)
        details.append(detail)
    return gaps, details


def _band_coverage(thresholds_path: Path, metrics: list[str]) -> tuple[list[str], str]:
    """Metrics without a band row; returns (missing, band_column_used)."""

    try:
        with open(thresholds_path, newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            band_column = next((c for c in BAND_COLUMN_CANDIDATES if c in fieldnames), None)
            if band_column is None:
                raise InputError(
                    f"thresholds: {thresholds_path} has no band column "
                    f"(need one of: {', '.join(BAND_COLUMN_CANDIDATES)})")
            if "metric" not in fieldnames:
                raise InputError(f"thresholds: {thresholds_path} has no 'metric' column")
            covered = {row.get("metric") for row in reader}
    except OSError as exc:
        raise InputError(f"thresholds: cannot read {thresholds_path}: {exc}") from None
    return [m for m in sorted(set(metrics)) if m not in covered], band_column


def _reference_gaps(reference: dict, cases: list[dict]) -> tuple[list[str], list[str]]:
    """Path/workload names the cases use but the reference scenario lacks."""

    ref_paths = set(reference.get("paths", {}))
    ref_workloads = set(reference.get("workloads", {}))
    used_paths: set[str] = set()
    used_workloads: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            continue
        for role in ("old_path", "new_path"):
            if case.get(role) is not None:
                used_paths.add(case[role])
        if case.get("workload") is not None:
            used_workloads.add(case["workload"])
    return sorted(used_paths - ref_paths), sorted(used_workloads - ref_workloads)


def build_report(manifest_path: Path, thresholds_path: Path, reference_path: Path) -> dict:
    manifest = _load_json(manifest_path, "manifest")
    reference = _load_json(reference_path, "reference")

    gaps: list[str] = []
    schema_gaps = _runner_schema_gaps(manifest)
    gaps.extend(schema_gaps)
    runner_executable = not schema_gaps

    cases = manifest.get("cases")
    case_list = cases if isinstance(cases, list) else []
    queue_gaps, case_details = _case_queue_gaps(manifest)
    gaps.extend(queue_gaps)

    metrics = []
    for case in case_list:
        if isinstance(case, dict):
            metrics.extend(case.get("metrics") or [])
    metrics_without_bands, band_column = _band_coverage(thresholds_path, metrics)
    for metric in metrics_without_bands:
        gaps.append(f"metric {metric!r} has no band row in {thresholds_path}")

    missing_ref_paths, missing_ref_workloads = _reference_gaps(reference, case_list)
    for name in missing_ref_paths:
        gaps.append(f"path {name!r} used by cases but not defined in reference {reference_path}")
    for name in missing_ref_workloads:
        gaps.append(f"workload {name!r} used by cases but not defined in reference {reference_path}")

    return {
        "manifest": str(manifest_path),
        "thresholds": str(thresholds_path),
        "reference": str(reference_path),
        "band_column": band_column,
        "runner_executable": runner_executable,
        "runner_note": (
            "manifest is directly loadable by testbed.scenario.load_scenario"
            if runner_executable else
            "manifest is NOT directly loadable by testbed.scenario.load_scenario"
        ),
        "cases": case_details,
        "metrics_without_bands": metrics_without_bands,
        "reference_missing_paths": missing_ref_paths,
        "reference_missing_workloads": missing_ref_workloads,
        "gaps": gaps,
        "scientific_validity": "not_evaluated",
        "disclaimer": DISCLAIMER,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-engine manifest gap diagnostic (mechanical only; "
        "no scientific validation, no scenario construction)."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST,
                        help=f"case manifest (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS,
                        help=f"thresholds CSV (default: {DEFAULT_THRESHOLDS})")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE,
                        help=f"reference scenario (default: {DEFAULT_REFERENCE})")
    parser.add_argument("--json", action="store_true",
                        help="print the report as a single JSON object")
    args = parser.parse_args(argv)

    try:
        report = build_report(args.manifest, args.thresholds, args.reference)
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"manifest: {report['manifest']}")
        print(f"runner_executable: {str(report['runner_executable']).lower()} ({report['runner_note']})")
        print(f"band column: {report['band_column']}")
        if report["gaps"]:
            print("gaps:")
            for gap in report["gaps"]:
                print(f"  - {gap}")
        else:
            print("gaps: none")
        print(f"scientific_validity: {report['scientific_validity']}")
        print(DISCLAIMER)
    return 1 if report["gaps"] else 0


if __name__ == "__main__":
    sys.exit(main())
