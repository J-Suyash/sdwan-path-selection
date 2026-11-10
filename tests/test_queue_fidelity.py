"""Queue model fidelity tests (verification round item 1).

Pin the exact units, buffer semantics, service-rate handling and the
1250 ms queue-delay ceiling mechanism. These tests document behaviour;
they do not assert that the behaviour is desirable.
"""

import numpy as np
import pytest

from env import SDWanConfig, SDWanEnv
from env.queue import FluidQueue
from env.traces import build_series


def test_buffer_is_fixed_bytes_of_ceiling_service():
    """Buffer size = cap_mbps * queue_buffer_s in bytes, fixed at reset."""

    cfg = SDWanConfig(primary_profile="medium")
    cap = cfg.cap_mbps["five_g"]
    q = FluidQueue(buffer_bytes=cap * 1e6 / 8.0 * cfg.queue_buffer_s)
    assert q.buffer_bytes == cap * 1e6 / 8.0 * 0.25
    # Occupancy is clamped to the buffer on construction and in step()
    # (assignment to the mutable attribute bypasses the clamp, which is
    # why the env only ever writes occupancy through step()).
    clamped = FluidQueue(buffer_bytes=1000.0, occupancy_bytes=5000.0)
    assert clamped.occupancy_bytes == 1000.0


def test_step_units_and_conservation():
    """offered bytes = Mbps * 1e6 / 8 * dt; conservation holds exactly."""

    q = FluidQueue(buffer_bytes=1_000_000.0)
    qs = q.step(offered_mbps=10.0, capacity_mbps=5.0, dt_s=1.0)
    assert qs.offered_bytes == pytest.approx(10.0 * 1e6 / 8.0)
    assert qs.capacity_bytes == pytest.approx(5.0 * 1e6 / 8.0)
    # Nothing prior in the queue: everything not served is dropped or queued.
    assert qs.offered_bytes == pytest.approx(
        qs.delivered_bytes + qs.dropped_bytes + qs.occupancy_bytes
    )


def test_backlog_drains_before_new_arrivals():
    """Drain-first accounting attributes overflow drops to arrivals once."""

    q = FluidQueue(buffer_bytes=1_000_000.0)
    q.step(offered_mbps=10.0, capacity_mbps=0.0, dt_s=1.0)  # all queued
    assert q.occupancy_bytes == 1_000_000.0  # rest dropped at admission
    qs = q.step(offered_mbps=10.0, capacity_mbps=5.0, dt_s=1.0)
    served = 5.0 * 1e6 / 8.0  # backlog drained first
    assert qs.delivered_bytes == pytest.approx(served)
    # Offered traffic exceeds the freed space: buffer refills to full and
    # the remainder is dropped exactly once.
    assert q.occupancy_bytes == pytest.approx(1_000_000.0)
    assert qs.dropped_bytes == pytest.approx(qs.offered_bytes - served)


def test_queue_delay_ceiling_from_capacity_floor():
    """The reported 1250 ms ceiling: fixed buffer sized at ceiling rate,
    service rate sagging to the 20% floor.

    traces.py floors trace capacity at cap_mbps * 0.2; a backlog that
    filled at ceiling rate then drains against the floor, and
    _class_qos reports occupancy / floor_rate:
        queue_buffer_s / 0.2 * 1000 = 1250 ms  (for 0.25 s buffer)
    """

    cap = 300.0  # five_g ceiling
    buffer_s = 0.25
    q = FluidQueue(buffer_bytes=cap * 1e6 / 8.0 * buffer_s)
    for _ in range(3):
        q.step(offered_mbps=400.0, capacity_mbps=cap, dt_s=1.0)
    assert q.occupancy_bytes == q.buffer_bytes  # saturated
    q.step(offered_mbps=400.0, capacity_mbps=cap * 0.2, dt_s=1.0)
    # Env delay formula: occupancy_bytes / (capacity_mbps * 1e6 / 8) * 1000
    delay_ms = q.occupancy_bytes / (cap * 0.2 * 1e6 / 8.0) * 1000.0
    assert delay_ms == pytest.approx(buffer_s / 0.2 * 1000.0)
    assert delay_ms == pytest.approx(1250.0)


def test_env_queue_delay_reflects_instantaneous_service_rate():
    """_class_qos divides the *end-of-step* occupancy snapshot by the
    current step's trace capacity (instantaneous service rate)."""

    import dataclasses

    cfg = SDWanConfig(episode_seconds=4, primary_profile="small")
    cfg.underlay_source = {u: f"nonexistent-{u}" for u in cfg.underlays}
    env = SDWanEnv(cfg, seed=1)
    env.reset(seed=1)
    underlay = env.assignment["voice"]
    idx = env.t
    capacity = float(env.series[underlay]["capacity"][idx])
    q = env.queues[underlay]
    # The env reads the per-step QueueStep snapshot, not the live queue.
    saturated = dataclasses.replace(
        env.queue_metrics[underlay],
        occupancy_bytes=q.buffer_bytes,
        capacity_bytes=capacity * 1e6 / 8.0 * env.cfg.decision_interval_s,
    )
    env.queue_metrics[underlay] = saturated
    info = env._class_qos("voice", idx)
    queue_delay_ms = q.buffer_bytes / (capacity * 1e6 / 8.0) * 1000.0
    rtt_ms = float(env.series[underlay]["rtt_ms"][idx])
    expected = rtt_ms * env.cfg.oneway_delay_factor + queue_delay_ms
    assert info["delay"] == pytest.approx(expected, rel=1e-6)


def test_capacity_floor_applied_in_trace_build():
    """Trace capacity is clamped to [0.2 * cap, cap]; outages zero it."""

    steps = 6
    rng = np.random.default_rng(0)
    df = None  # synthetic path: capacity capped by synthetic_series
    series = build_series(df, steps, rng, fallback_rtt_ms=50.0, cap_mbps=100.0)
    assert (series["capacity"] <= 100.0 + 1e-9).all()
    assert (series["capacity"] >= 20.0 - 1e-9).all()  # 20% floor


def test_matched_mode_queue_mapping():
    """Cross-engine matched mode: emulator buffers mirror the testbed's
    per-path packet limits (limit_packets * packet_bytes)."""

    limits = {"bb": 4166, "five_g": 3125, "leo": 2083}
    packet_bytes = 1400
    cfg = SDWanConfig(
        primary_profile="medium",
        queue_buffer_bytes={u: limits[u] * packet_bytes for u in limits},
    )
    assert cfg.queue_buffer_bytes["five_g"] == 3125 * 1400
    env = SDWanEnv(cfg, seed=1)
    env.reset(seed=1)
    for underlay in env.cfg.underlays:
        assert env.queues[underlay].buffer_bytes == pytest.approx(
            limits[underlay] * packet_bytes
        )


def test_matched_mode_validation():
    with pytest.raises(ValueError, match="missing underlays"):
        SDWanConfig(queue_buffer_bytes={"bb": 1000.0})
    with pytest.raises(ValueError, match="must be positive"):
        SDWanConfig(queue_buffer_bytes={"bb": 0.0, "five_g": 1.0, "leo": 1.0})
