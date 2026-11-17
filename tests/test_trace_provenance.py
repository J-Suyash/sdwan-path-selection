"""Trace provenance is explicit: the synthetic fallback is recorded,
surfaced in ``info`` and can be refused, so a green run cannot silently
misrepresent its inputs."""

from pathlib import Path

import pytest

from env import SDWanConfig, SDWanEnv

DATA_ROOT = Path("data/processed")
SOURCE_FILES = ["collected.parquet", "lumos5g.parquet", "wetlinks.parquet"]


def _reset(cfg: SDWanConfig, seed: int = 0):
    env = SDWanEnv(cfg, seed=seed)
    _, info = env.reset(seed=seed)
    return env, info


def test_synthetic_fallback_is_recorded_and_surfaced(tmp_path):
    """No parquet files -> synthetic, and every surface says so."""
    cfg = SDWanConfig(data_root=str(tmp_path))
    env, info = _reset(cfg)
    assert set(env.trace_provenance.values()) == {"synthetic"}
    assert all(v == "synthetic" for v in env.trace_window_start.values())
    assert info["trace_provenance"] == env.trace_provenance
    assert info["trace_window_start"] == env.trace_window_start


def test_synthetic_fallback_can_be_refused(tmp_path):
    cfg = SDWanConfig(data_root=str(tmp_path), allow_synthetic_traces=False)
    with pytest.raises(RuntimeError, match="allow_synthetic_traces"):
        SDWanEnv(cfg, seed=0).reset(seed=0)


@pytest.mark.skipif(
    not all((DATA_ROOT / name).exists() for name in SOURCE_FILES),
    reason="processed trace parquets absent; link data/processed first",
)
def test_real_traces_are_labelled_real():
    """With the processed parquets present, default config uses them."""
    env, info = _reset(SDWanConfig())
    assert set(env.trace_provenance.values()) == {"real"}
    assert all(v != "synthetic" for v in env.trace_window_start.values())
    assert set(info["trace_provenance"].values()) == {"real"}
