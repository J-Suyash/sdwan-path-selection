"""Offline tests for the during-send cadence clock sampler."""
import threading
import time

import pytest

from testbed.run_switch_calibration import cadence_sampler


def _run_sampler(cadence_s, run_s):
    samples = []
    lock = threading.Lock()
    stop = threading.Event()
    t0 = time.monotonic()
    thread = threading.Thread(target=cadence_sampler, args=(t0, stop, samples, lock, cadence_s), daemon=True)
    thread.start()
    time.sleep(run_s)
    stop.set()
    thread.join(timeout=2.0)
    return t0, samples


def test_records_ticks_with_honest_timestamps():
    t0, samples = _run_sampler(cadence_s=0.05, run_s=0.18)
    assert len(samples) >= 2
    for sample in samples:
        assert sample["label"].startswith("cadence_")
        assert abs((sample["epoch_after_s"] - sample["epoch_before_s"]) - sample["sampling_bracket_s"]) < 1e-9
        assert sample["sampling_bracket_s"] >= 0.0
        assert sample["epoch_before_s"] > 1e9  # wall-clock epoch, not monotonic
        assert sample["monotonic_s"] >= t0
        assert "nominal_tick_offset_s" in sample
        assert abs(sample["cadence_lateness_s"]) < 0.2
        assert sample["cadence_lateness_s"] == pytest.approx(
            sample["monotonic_s"] - (t0 + sample["nominal_tick_offset_s"]), abs=1e-9)
    monotonics = [s["monotonic_s"] for s in samples]
    assert monotonics == sorted(monotonics)
    # First tick lands near t0 + cadence, not at t0.
    assert abs(monotonics[0] - (t0 + 0.05)) < 0.05


def test_tick_spacing_matches_cadence():
    _, samples = _run_sampler(cadence_s=0.05, run_s=0.24)
    monotonics = [s["monotonic_s"] for s in samples]
    spacings = [b - a for a, b in zip(monotonics, monotonics[1:])]
    assert spacings, "expected multiple cadence samples"
    for spacing in spacings:
        assert 0.02 < spacing < 0.15


def test_stop_before_first_tick_records_nothing():
    samples = []
    lock = threading.Lock()
    stop = threading.Event()
    t0 = time.monotonic() + 60.0  # first tick far in the future
    thread = threading.Thread(target=cadence_sampler, args=(t0, stop, samples, lock, 1.0), daemon=True)
    thread.start()
    stop.set()
    thread.join(timeout=2.0)
    assert not thread.is_alive()
    assert samples == []


def test_real_cadence_labels_are_unique_and_numbered():
    samples = []
    lock = threading.Lock()
    stop = threading.Event()
    t0 = time.monotonic()
    thread = threading.Thread(target=cadence_sampler, args=(t0, stop, samples, lock, 1.0), daemon=True)
    thread.start()
    time.sleep(2.3)
    stop.set()
    thread.join(timeout=2.0)
    labels = [s["label"] for s in samples]
    assert labels == ["cadence_01s", "cadence_02s"]
    assert abs(samples[0]["monotonic_s"] - (t0 + 1.0)) < 0.2
