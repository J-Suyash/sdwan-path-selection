import numpy as np
import pandas as pd
import pytest

from env import (
    DEFAULT_BRANCH_PROFILES,
    FluidQueue,
    SDWanConfig,
    SDWanEnv,
    WorkloadGenerator,
)
from offline.ope import fqe, support_report, wis


def test_queue_is_bounded_and_conserves_arrivals():
    queue = FluidQueue(buffer_bytes=100.0)
    for offered, capacity in [(10.0, 0.0), (0.0, 10.0), (5.0, 1.0)]:
        step = queue.step(offered, capacity, 0.5)
        assert 0.0 <= step.occupancy_bytes <= queue.buffer_bytes
        assert np.isclose(step.offered_bytes, step.admitted_bytes + step.dropped_bytes)
        # Delivery can include backlog admitted in an earlier step.
        assert step.delivered_bytes >= 0.0


def test_workload_relationships_and_censoring_are_explicit():
    generator = WorkloadGenerator(
        DEFAULT_BRANCH_PROFILES["medium"], np.random.default_rng(4)
    )
    generator.reset(9.0)
    for t in range(1, 200):
        generator.advance(float(t), 1.0)
    assert generator.sessions
    assert generator.flows
    for session in generator.sessions.values():
        assert session.flow_ids
        assert all(
            generator.flows[f].session_id == session.session_id
            for f in session.flow_ids
        )


def test_natural_completion_is_not_marked_censored():
    generator = WorkloadGenerator(
        DEFAULT_BRANCH_PROFILES["small"], np.random.default_rng(5)
    )
    generator.reset(8.0)
    session = generator._make_session(1.0, "voice", generator.users[0])

    generator.advance(session.end_s - 1e-6, 1e-6)
    assert session.active
    assert not session.censored

    snapshot = generator.advance(session.end_s, 1.0)
    assert snapshot.terminated_sessions == 1
    assert snapshot.censored_sessions == 0
    assert session.terminated_s == session.end_s
    assert not session.censored
    assert all(
        generator.flows[flow_id].terminated_s == session.end_s
        for flow_id in session.flow_ids
    )


def test_boundary_censoring_is_recorded_for_sessions_and_flows():
    generator = WorkloadGenerator(
        DEFAULT_BRANCH_PROFILES["small"], np.random.default_rng(6)
    )
    generator.reset(8.0)
    session = generator._make_session(100.0, "video", generator.users[0])
    horizon = 110.0

    result = generator.finalize(horizon)
    assert result["censored_sessions"] == 1
    assert result["censored_flows"] == len(session.flow_ids)
    assert session.terminated_s == horizon
    assert session.censored
    assert all(generator.flows[flow_id].censored for flow_id in session.flow_ids)
    report = generator.lifecycle_report()
    assert report["sessions"]["censored"] == 1
    assert report["flows"]["censored"] == len(session.flow_ids)


def test_environment_replay_and_queue_metadata():
    cfg = SDWanConfig(episode_seconds=8, primary_profile="small")
    left = SDWanEnv(cfg, seed=7)
    right = SDWanEnv(cfg, seed=7)
    obs_l, _ = left.reset(seed=7)
    obs_r, _ = right.reset(seed=7)
    assert np.array_equal(obs_l, obs_r)
    for action in [0, 17, 80, 2, 45, 0, 10, 1]:
        obs_l, _, _, _, info_l = left.step(action)
        obs_r, _, _, _, info_r = right.step(action)
        assert np.array_equal(obs_l, obs_r)
        assert info_l["queue"].keys() == info_r["queue"].keys()
        for q in info_l["queue"].values():
            assert q["occupancy_bytes"] >= 0
            assert q["admitted_bytes"] >= q["delivered_bytes"]
    assert info_l["switching_calibrated"] is False
    assert info_l["lifecycle"]["sessions"] == info_r["lifecycle"]["sessions"]
    assert info_l["lifecycle"]["flows"] == info_r["lifecycle"]["flows"]
    assert info_l["active_sessions"] == info_l["lifecycle"]["sessions"]["active"]
    assert info_l["active_flows"] == info_l["lifecycle"]["flows"]["active"]


def test_non_unit_decision_interval_preserves_episode_duration():
    cfg = SDWanConfig(
        episode_seconds=6,
        decision_interval_s=2.0,
        history_s=3,
        primary_profile="small",
    )
    env = SDWanEnv(cfg, seed=3)
    env.reset(seed=3)
    assert cfg.episode_steps == 3
    assert cfg.history_steps == 2
    assert len(env.series["bb"]["rtt_ms"]) == 3

    for step in range(cfg.episode_steps):
        _, _, terminated, _, info = env.step(0)
        assert terminated is (step == cfg.episode_steps - 1)
    assert info["t"] == 3
    assert env.t * cfg.decision_interval_s == cfg.episode_duration_s


def test_episode_duration_must_align_with_decision_interval():
    with pytest.raises(ValueError, match="integer multiple"):
        SDWanConfig(episode_seconds=5, decision_interval_s=2.0)


def test_oneway_delay_maps_round_trip_rtt_against_one_way_sla():
    """Regression for the RTT / one-way delay semantics fix.

    All trace delay inputs are round-trip ping measurements; the SLA delay
    thresholds are one-way (ITU-T G.114). A round-trip of 188 ms must map
    to 94 ms one-way, not breach the 150 ms voice delay threshold by
    itself.
    """
    cfg = SDWanConfig(episode_seconds=4, primary_profile="small")
    cfg.fallback_rtt_ms = {"bb": 188.0, "five_g": 40.0, "leo": 60.0}
    env = SDWanEnv(cfg, seed=1)
    env.reset(seed=1)
    for step in range(cfg.episode_steps):
        _, _, _, _, info = env.step(0)
    # Load, loss or outage could still violate independently; assert the
    # delay component explicitly instead of only the violation flag.
    delay = info["per_class"]["voice"]["delay"]
    assert delay < cfg.sla["voice"][0]
    assert env.cfg.oneway_delay_factor == 0.5


def test_oneway_delay_factor_is_validated():
    with pytest.raises(ValueError, match="oneway_delay_factor"):
        SDWanConfig(oneway_delay_factor=0.0)


def test_switching_interruption_uses_simulation_seconds(tmp_path):
    calibration = tmp_path / "switching.csv"
    pd.DataFrame(
        [
            {
                "old_rtt_ms": 30,
                "new_rtt_ms": 40,
                "old_jitter_ms": 1,
                "new_jitter_ms": 1,
                "packets_in_flight": 1,
                "flow_type": "voice",
                "transport": "udp",
                "queue_occupancy_frac": 0,
                "interruption_s": 3,
                "loss_frac": 0.5,
                "reordering_frac": 0,
            }
        ]
    ).to_csv(calibration, index=False)
    cfg = SDWanConfig(
        episode_seconds=6,
        decision_interval_s=2.0,
        primary_profile="small",
        switching_calibration_path=str(calibration),
    )
    env = SDWanEnv(cfg, seed=4)
    env.reset(seed=4)

    _, _, _, _, info_at_0 = env.step(1)
    _, _, _, _, info_at_2 = env.step(1)
    _, _, _, _, info_at_4 = env.step(1)
    # Switch at t=0, interruption 3 s, step interval 2 s:
    # step 0 keeps the full measured effect (frac 1.0), step 2 is a
    # partial step (frac 0.5 -> 1 - (1-l)*sqrt(1-L)), step 4 is clean.
    loss_0 = info_at_0["per_class"]["voice"]["loss"]
    loss_2 = info_at_2["per_class"]["voice"]["loss"]
    loss_4 = info_at_4["per_class"]["voice"]["loss"]
    assert loss_0 >= 0.5
    assert loss_2 < loss_0  # partial-step fraction reduces the effect
    assert loss_4 < 0.5


def test_sub_second_switching_fractional_transients_are_prorated(tmp_path):
    """Measured transients shorter than one decision step now count.

    Regression: with a per-second binary rupture flag, the measured
    sub-second Mininet interruptions (0.002-0.18 s) were invisible in the
    emulator. The prorated exposure applies the measured effect to the
    interrupted fraction of the step only.
    """

    calibration = tmp_path / "switching.csv"
    pd.DataFrame(
        [
            {
                "old_rtt_ms": 187,
                "new_rtt_ms": 75,
                "old_jitter_ms": 1,
                "new_jitter_ms": 1,
                "packets_in_flight": 20,
                "flow_type": "voice",
                "transport": "udp",
                "queue_occupancy_frac": 0,
                "interruption_s": 0.07,
                "loss_frac": 0.5,
                "reordering_frac": 0,
            }
        ]
    ).to_csv(calibration, index=False)
    cfg = SDWanConfig(
        episode_seconds=4,
        decision_interval_s=1.0,
        primary_profile="small",
        switching_calibration_path=str(calibration),
    )
    env = SDWanEnv(cfg, seed=1)
    env.reset(seed=1)
    _, _, _, _, info = env.step(1)
    first_loss = info["per_class"]["voice"]["loss"]
    _, _, _, _, info2 = env.step(1)
    second_loss = info2["per_class"]["voice"]["loss"]
    # Fractional exposure must be strictly between nothing and a full repose.
    assert first_loss > second_loss
    assert first_loss < 0.5  # 0.07 of the step interrupted only


def test_stress_regime_override_is_reproducible():
    env = SDWanEnv(
        SDWanConfig(
            episode_seconds=2, primary_profile="small", workload_regime="stress"
        ),
        seed=2,
    )
    env.reset(seed=2)
    assert env.workload._regime(0.0) == "stress"


def test_wis_reports_effective_sample_size_and_support():
    rows = []
    for episode in range(3):
        for t in range(2):
            rows.append(
                {
                    "policy": "epsilon",
                    "episode": episode,
                    "t": t,
                    "action": 0,
                    "reward": 1.0,
                    "behavior_action_prob": 0.5,
                }
            )
    frame = pd.DataFrame(rows)
    result = wis(frame, lambda row: 0.5, bootstrap=10, seed=1)
    assert np.isclose(result.estimate, 2.0)
    assert result.effective_sample_size == 3.0
    assert result.bootstrap_interval is not None
    assert support_report(frame, 2)["observed_actions"] == 1


def test_fqe_matches_constant_one_step_return():
    rows = []
    for episode in range(3):
        obs = np.array([float(episode), 1.0], dtype=np.float32)
        rows.append(
            {
                "policy": "baseline",
                "episode": episode,
                "t": 0,
                "obs": obs,
                "next_obs": obs,
                "action": 0,
                "reward": 2.0,
            }
        )
    result = fqe(pd.DataFrame(rows), lambda _: 0, n_actions=1, iterations=3)
    assert np.isclose(result.estimate, 2.0)
