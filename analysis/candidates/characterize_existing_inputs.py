"""Engineering-only dry-run and existing-input characterization, no Mininet."""
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from scripts.run_emulator_matched_case import matched_config, required_metrics_from_cases, run_case
from testbed.scenario import load_scenario

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data/switching_calibration_v2.csv"
CASES = ROOT / "testbed/scenarios/cross_engine_cases.json"
OUT = ROOT / "analysis/characterization/existing_inputs_20261118"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def table_check(path):
    if not path.exists():
        return None
    rows = list(csv.DictReader(path.open()))
    groups = {}
    for r in rows:
        key = (r.get("case"), r.get("metric"), r.get("estimator"), r.get("quality"))
        groups.setdefault(key, []).append(r["value"])
    return [{"key": list(k), "values": v, "bit_exact_repr_across_repetitions": len(set(v)) == 1} for k, v in groups.items()]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    original = json.loads(CASES.read_text())["cases"]
    for i in range(1, 5):
        path = ROOT / f"testbed/scenarios/case_drafts/ce{i:02d}.json"
        raw = json.loads(path.read_text())
        sc = load_scenario(path)
        name, wl = next(iter(sc.workloads.items()))
        cfg = matched_config(sc, name, str(CAL), drain=True)
        required = required_metrics_from_cases(sc.name, CASES)
        rec = {
            "scenario": sc.name, "scenario_path": str(path.relative_to(ROOT)),
            "scenario_sha256": sha(path), "original_case": original[i - 1],
            "paths": raw["paths"], "workload": raw["workloads"], "events": raw["events"],
            "seeds": list(range(5)), "repetitions": sc.repetitions,
            "calibration_path": str(CAL.relative_to(ROOT)), "calibration_sha256": sha(CAL),
            "calibration_role": "existing switch-effect model input, not independent validation evidence",
            "required_metrics": required, "drain_opt_in": True,
            "load_stop_s": cfg.load_stop_s, "event_s": wl.warmup_s,
            "max_episode_s": cfg.episode_seconds, "decision_interval_s": cfg.decision_interval_s,
            "nominal_capacity_mbps": {p: s.capacity_mbps for p, s in sc.paths.items()},
            "matched_payload_capacity_mbps": dict(cfg.cap_mbps),
            "capacity_scale": wl.packet_bytes / 1442.0,
            "queue_buffer_payload_bytes": dict(cfg.queue_buffer_bytes),
            "emulator_endpoints": "step 0 to first post-load step with summed residual below one packet, or scaled 3*max_buffer/min_service bound",
            "runner_endpoint_status": "opt-in --matched-drain: common anchored inspection-grid definition, actual host sampling times and lateness reported; no denominator equality assumed",
            "case_interpretation": ("sustained sag from event to end is a working interpretation, not recovered original intent" if i == 1 else "existing switch inputs, case names do not prove boundary coverage"),
            "send_duration_interpretation": "14s send duration; warmup/event at 6s is within it, not an additional 6s",
            "candidate_estimators": "full episode per-step time weighting, including opt-in drain; informational, no estimator tuning or acceptance",
            "status": "dry_run_only"
        }
        if args.run:
            dest = OUT / f"ce{i:02d}"
            code = run_case(path, calibration_path=str(CAL), out_dir=dest, seed=0, cases_path=CASES, drain=True)
            rec["status"] = "engineering_debug_only"
            rec["exit_code"] = code
            rec["coverage"] = json.loads((dest / "coverage.json").read_text())
            rec["run_manifest"] = json.loads((dest / "run_manifest.json").read_text())
            rec["numeric_check"] = table_check(dest / "emulator_metrics.partial.csv") or table_check(dest / "emulator_metrics.csv")
            rec["candidate_check"] = table_check(dest / "emulator_estimator.csv")
            rec["informative_check"] = table_check(dest / "emulator_informative.csv")
        records.append(rec)
    artifact = {
        "label": "raw_unvalidated_scaffolding", "purpose": "existing-input engineering characterization, never boundary validation or result acceptance",
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "harness_sha256": sha(ROOT / "scripts/run_emulator_matched_case.py"),
        "generator_sha256": sha(Path(__file__)),
        "cases_source_sha256": sha(CASES), "calibration_heldout_separation": "no bands derived, no acceptance decisions; future calibration rules must freeze before held-out evaluation",
        "privileged_execution": False, "records": records
    }
    target = OUT / ("characterization.json" if args.run else "dry_run_manifest.json")
    target.write_text(json.dumps(artifact, indent=2) + "\n")
    print(str(target.relative_to(ROOT)))
    if args.run:
        for r in records:
            print(r["scenario"], "exit", r["exit_code"], "coverage", {k: v["status"] for k, v in r["coverage"]["required_metrics"].items()})


if __name__ == "__main__":
    main()
