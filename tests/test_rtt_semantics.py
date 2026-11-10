"""RTT / one-way-delay semantics regression battery (spec section 3).

Pinpoints: the single application of the 0.5 one-way factor, its absence
from observation features (raw RTT preserved), the one-way-input mode
(factor 1.0), the missing-RTT policy, and controller/emulator agreement.
"""

import numpy as np
import pandas as pd
import pytest

from env import SDWanConfig, SDWanEnv
from env.traces import _fill_nan
from policies.incumbents import link_ok


def _tiny_cfg(**kwargs) -> SDWanConfig:
    cfg = SDWanConfig(episode_seconds=4, primary_profile="small", **kwargs)
    # Force the synthetic fallback path: the real collected/raca/wetlinks
    # parquet traces would otherwise take over and shift absolute delays.
    cfg.underlay_source = {u: f"nonexistent-{u}" for u in cfg.underlays}
    return cfg


def test_rtt_200_maps_to_oneway_100():
    cfg = _tiny_cfg()
    assert 200.0 * cfg.oneway_delay_factor == 100.0


def test_factor_applied_once_in_emulator_delay():
    cfg = _tiny_cfg()
    cfg.fallback_rtt_ms = {"bb": 200.0, "five_g": 200.0, "leo": 200.0}
    env = SDWanEnv(cfg, seed=3)
    env.reset(seed=3)
    _, _, _, _, info = env.step(0)
    # With no queue build-up the per-class delay must be exactly one
    # application of the factor on the recorded (random-walking) RTT.
    recorded = env.series["bb"]
    delay_recorded_raw = float(recorded["rtt_ms"][0])
    assert info["per_class"]["voice"]["delay"] == pytest.approx(
        delay_recorded_raw * 0.5, rel=1e-4
    )
    assert delay_recorded_raw > 100.0  # walk around fallback 200, not halved
    assert env.cfg.oneway_delay_factor == 0.5  # untouched by evaluation


def test_raw_rtt_is_preserved_in_observations():
    cfg = _tiny_cfg()
    cfg.fallback_rtt_ms = {"bb": 200.0, "five_g": 90.0, "leo": 70.0}
    env = SDWanEnv(cfg, seed=3)
    env.reset(seed=3)
    rtt_obs_mean = float(env._observe()[0])
    history_mean = float(
        np.mean([h[0] for h in env.history["bb"]])
    )
    # Features carry the raw round-trip mean, not a halved value.
    assert rtt_obs_mean == pytest.approx(history_mean, rel=1e-4)
    assert abs(rtt_obs_mean - 200.0) < 5.0  # walks around 200, stays huge


def test_oneway_input_not_halved():
    """factor 1.0 = delay inputs already one-way; no conversion applied."""

    cfg = _tiny_cfg(oneway_delay_factor=1.0)
    cfg.fallback_rtt_ms = {"bb": 100.0, "five_g": 100.0, "leo": 100.0}
    env = SDWanEnv(cfg, seed=5)
    env.reset(seed=5)
    _, _, _, _, info = env.step(0)
    recorded = float(env.series["bb"]["rtt_ms"][0])
    assert info["per_class"]["voice"]["delay"] == pytest.approx(recorded, rel=1e-4)


def test_missing_rtt_not_zeroed():
    all_nan = np.array([np.nan, np.nan, np.nan, np.nan])
    filled = _fill_nan(all_nan, 400.0)
    assert (filled == 400.0).all()

    gappy = np.array([np.nan, 50.0, np.nan, 90.0])
    interpolated = _fill_nan(gappy, 400.0)
    assert interpolated[0] == pytest.approx(50.0)
    assert interpolated[2] == pytest.approx(70.0)
    assert not (gappy == 0).any()

def test_fallback_rtt_must_be_positive():
    with pytest.raises(ValueError):
        SDWanConfig(fallback_rtt_ms={"bb": 0.0, "five_g": 40.0, "leo": 60.0})


def test_controller_and_emulator_delay_semantics_match():
    """link_ok halves RTT exactly as the emulator's SLA check does."""

    cfg = _tiny_cfg()
    cfg.fallback_rtt_ms = {"bb": 188.0, "five_g": 40.0, "leo": 60.0}
    env = SDWanEnv(cfg, seed=9)
    env.reset(seed=9)
    # Wholesale: only the bb leg, with window mean rtt 188 -> 94 one-way.
    ok_delay = link_ok(env, "voice", "bb")
    mean_rtt = float(np.mean([h[0] for h in env.history["bb"]]))
    expected = (mean_rtt * cfg.oneway_delay_factor) <= cfg.sla["voice"][0]
    assert abs(mean_rtt - 188.0) < 3.0  # walk inside fallback band
    assert ok_delay == expected


def test_recorded_rttfix_evidence_referenced():
    """The documented ranking/safety-change rows exist in analysis outputs."""

    frame = pd.read_csv("analysis/delay_semantics_reassessment.csv")
    voice = frame.loc[
        frame["algo"] == "rttfix_threshold_hysteresis", "viol_voice_per_h"
    ]
    assert set(voice.round()) == {80.0, 952.0, 1.0}
