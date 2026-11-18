"""Emulator-only control+contrast characterization, no Mininet, unprivileged.

Condition A: ce01_control_nosag.json (no capacity event; offered below capacity).
Condition B: ce01.json unchanged (sag into saturation).
All artifacts are raw_unvalidated_scaffolding: diagnostic leads only.
"""
import hashlib
import json
from pathlib import Path

from scripts.run_emulator_matched_case import matched_config, required_metrics_from_cases, run_case
from testbed.scenario import load_scenario

ROOT = Path(__file__).resolve().parents[1]
CAL = ROOT / "data/switching_calibration_v2.csv"
CASES = ROOT / "testbed/scenarios/cross_engine_cases.json"
OUT = ROOT / "analysis/characterization/control_contrast_20261118"

CONDITIONS = {
    "A_control_nosag": "testbed/scenarios/case_drafts/ce01_control_nosag.json",
    "B_contrast_sag": "testbed/scenarios/case_drafts/ce01.json",
}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    records = {}
    for label, rel in CONDITIONS.items():
        path = ROOT / rel
        sc = load_scenario(path)
        name, wl = next(iter(sc.workloads.items()))
        cfg = matched_config(sc, name, str(CAL), drain=True)
        dest = OUT / label
        code = run_case(path, calibration_path=str(CAL), out_dir=dest, seed=0, cases_path=CASES, drain=True)
        rec = {
            "condition": label,
            "scenario_path": rel,
            "scenario_sha256": sha(path),
            "events": json.loads(path.read_text())["events"],
            "exit_code": code,
            "load_stop_s": cfg.load_stop_s,
            "max_episode_s": cfg.episode_seconds,
            "nominal_capacity_mbps": {p: s.capacity_mbps for p, s in sc.paths.items()},
            "matched_payload_capacity_mbps": dict(cfg.cap_mbps),
            "status": "engineering_debug_only",
        }
        for fname in ("emulator_metrics.csv", "emulator_metrics.partial.csv",
                      "emulator_estimator.csv", "emulator_informative.csv"):
            f = dest / fname
            if f.exists():
                rec[fname] = f.read_text()
        cov = dest / "coverage.json"
        if cov.exists():
            rec["coverage"] = json.loads(cov.read_text())
        records[label] = rec
    (OUT / "control_contrast_characterization.json").write_text(json.dumps({
        "label": "raw_unvalidated_scaffolding",
        "purpose": "emulator-only control/contrast characterization; diagnostic leads, never validation or acceptance",
        "conditions": records,
    }, indent=2) + "\n")
    for label, rec in records.items():
        print("==", label, "exit", rec["exit_code"])
        for fname in ("emulator_metrics.csv", "emulator_metrics.partial.csv"):
            if fname in rec:
                print(rec[fname])


if __name__ == "__main__":
    main()
