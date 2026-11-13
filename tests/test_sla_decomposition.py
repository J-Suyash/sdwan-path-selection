"""SLA decomposition verification (round item 2).

- The diagnostic re-diagnosis must not alter environment state or counters.
- The committed decomposition artefact must be reproducible from raw
  env transitions (one factor re-run end-to-end).
"""

import dataclasses

import numpy as np
import pandas as pd
import pytest

from env import SDWanConfig, SDWanEnv
from policies.incumbents import ThresholdHysteresis
from scripts.decompose_sla_violations import diagnose


def _config() -> SDWanConfig:
    cfg = SDWanConfig(primary_profile="medium")
    cfg.switching_calibration_path = "data/switching_calibration.csv"
    return cfg


def _snapshot(env: SDWanEnv) -> dict:
    return {
        "violations": dict(env.violations),
        "recent": {c: list(env.recent_violations[c]) for c in env.cfg.classes},
        "t": env.t,
        "cum_cost": env.cum_cost,
        "assignment": dict(env.assignment),
        "disrupt_until": dict(env.disrupt_until),
        "queue_metrics": {
            u: dataclasses.asdict(env.queue_metrics[u]) for u in env.cfg.underlays
        },
        "loads": dict(env.load),
    }


def test_diagnose_preserves_env_state_exactly():
    env = SDWanEnv(_config(), seed=0)
    env.reset(seed=0)
    policy = ThresholdHysteresis()
    policy.reset(env)
    for _ in range(12):
        _, _, terminated, _, _ = env.step(int(policy.act(env)))
        before = _snapshot(env)
        diagnose(env)
        assert _snapshot(env) == before, "diagnose mutated environment state"
        if terminated:
            break


def test_diagnose_does_not_diverge_trajectory():
    """Two identical envs: one diagnosed every step, one not — the full
    trajectories must be identical."""

    results = []
    for diagnosed in (False, True):
        env = SDWanEnv(_config(), seed=7)
        env.reset(seed=7)
        policy = ThresholdHysteresis()
        policy.reset(env)
        violations = []
        for _ in range(30):
            _, _, terminated, _, info = env.step(int(policy.act(env)))
            if diagnosed:
                diagnose(env)
            violations.append(dict(info["violations"]))
            if terminated:
                break
        results.append((violations, env.cum_cost, env.t))
    assert results[0] == results[1]


@pytest.mark.sla_traces
def test_decomposition_reproduces_violations_from_raw_transitions():
    """Re-run the reference factor (0.5) from scratch: seed-level voice
    violation counts must match the committed CSV (80 / 952 / 1)."""

    cfg = _config()
    cfg.oneway_delay_factor = 0.5
    policy = ThresholdHysteresis()
    probe = SDWanEnv(cfg)  # same loaders as the re-runs below
    probe.reset(seed=0)
    missing = sorted(u for u, w in probe.trace_window_start.items() if w == "synthetic")
    if missing:
        pytest.skip(
            f"synthetic trace fallback active for {missing}: the 80/952/1 "
            "counts are recorded against real traces and cannot be "
            "reproduced from the synthetic random-walk path. See "
            "data/README.md to obtain the raw sources and rebuild the "
            "missing parquets with: python scripts/preprocess_traces.py all"
        )
    per_seed_voice, total_rows = [], 0
    for seed in range(3):
        env = SDWanEnv(cfg, seed=seed)
        env.reset(seed=seed)
        policy.reset(env)
        rows = []
        while True:
            _, _, terminated, _, _ = env.step(int(policy.act(env)))
            rows.extend(diagnose(env))
            if terminated:
                break
        frame = pd.DataFrame(rows)
        total_rows += len(frame)
        assert len(frame) == 3600 * 4  # 3600 steps x 4 classes
        per_seed_voice.append(
            int(frame[frame["class"] == "voice"]["violated"].sum())
        )
    assert per_seed_voice == [80, 952, 1]
    assert total_rows == 3 * 3600 * 4


def test_committed_decomposition_rates_and_denominators():
    """Rates from the committed artefact with explicit denominators."""

    frame = pd.read_csv("analysis/sla_violation_decomposition.csv")
    # 3 factors x 3 seeds x 3600 steps x 4 classes = 129,600 rows.
    assert len(frame) == 129_600
    by_factor = frame.groupby("oneway_delay_factor")["violated"].sum()
    assert (by_factor == 3079).all()

    # Denominator per (factor, seed): 3600 steps x 4 classes = 14,400
    # class-steps per seed; per class: 3600 class-steps = 1 hour episode.
    for factor, seed in [(0.5, 0), (0.5, 1), (0.5, 2)]:
        sub = frame[(frame.oneway_delay_factor == factor) & (frame.seed == seed)]
        assert len(sub) == 14_400
        voice = sub[sub["class"] == "voice"]
        viol_h = voice["violated"].sum() / 1.0  # 3600 class-steps = 1 h
        assert viol_h == {0: 80.0, 1: 952.0, 2: 1.0}[seed]

    # Cause flags are multi-label and only meaningful on violated rows
    # (non-violated rows report all causes False by construction).
    violated = frame[frame["violated"]]
    assert violated["cause_outage"].sum() == 0
    assert violated["cause_delay_trace"].sum() == 0
    assert (violated["cause_delay_queue"] > violated["violated"]).sum() == 0

    # The 861 ms mean is over violated observations only.
    sub = violated[violated.oneway_delay_factor == 0.5]
    mean_violated = sub["queue_delay_ms"].mean()
    mean_all = frame[frame.oneway_delay_factor == 0.5]["queue_delay_ms"].mean()
    assert mean_violated == pytest.approx(861.06, abs=0.5)
    assert mean_all < mean_violated  # violated subset is the extreme tail
