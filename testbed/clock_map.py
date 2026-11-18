"""Sampled-clock envelope for mapped capture windows. Descriptive, no validation."""
from __future__ import annotations

from bisect import bisect_right
import struct


def classify_frame(time_s, lower_s, upper_s):
    if upper_s < lower_s:
        raise ValueError("window envelope must be ordered")
    if time_s < lower_s:
        return "before"
    if time_s > upper_s:
        return "after"
    return "inside"


def _sorted_samples(samples):
    if not samples:
        raise ValueError("clock samples are required")
    result = sorted(samples, key=lambda s: s["monotonic_s"])
    for left, right in zip(result, result[1:]):
        if right["monotonic_s"] < left["monotonic_s"]:
            raise ValueError("non-monotonic sampled clock data")
    return result


def map_boundary(samples, boundary_monotonic_s):
    """Sampled envelope [lower, upper], never a claimed exact timestamp.

    Envelope combines adjacent sampled epoch brackets and interpolation
    between observed monotonic samples. Sparse samples cannot prove that
    no wall-clock step/nonlinearity happened between samples; they only
    expose observed evidence and sampling uncertainty.
    """
    samples = _sorted_samples(samples)
    m = [s["monotonic_s"] for s in samples]
    i = bisect_right(m, boundary_monotonic_s)
    if i == 0:
        left = right = samples[0]
    elif i >= len(samples):
        left = right = samples[-1]
    else:
        left, right = samples[i-1], samples[i]
    # A boundary outside sampled range is extrapolation, unavailable.
    if not (m[0] <= boundary_monotonic_s <= m[-1]):
        raise ValueError("boundary outside sampled clock range")
    # Adjacent epoch brackets conservatively include the direct read pair.
    candidates = []
    for sample in (left, right):
        candidates.extend((sample["epoch_before_s"], sample["epoch_after_s"]))
    if left is not right:
        dm = right["monotonic_s"] - left["monotonic_s"]
        if dm <= 0:
            raise ValueError("invalid monotonic sample spacing")
        # Interpolate each adjacent epoch bracket endpoint separately.
        alpha = (boundary_monotonic_s - left["monotonic_s"]) / dm
        for key in ("epoch_before_s", "epoch_after_s"):
            candidates.append(left[key] + alpha * (right[key] - left[key]))
    return min(candidates), max(candidates)


def mapped_capture_counts(frame_epochs, samples, t0, t1, *, boundary_safety_s=0.001):
    """Descriptive lower/upper counts using the declared sampled envelope.

    boundary_safety_s is protocol-declared, not derived from outcomes. It
    handles ordinary same-host sampling/nonlinearity only when no observed
    step is detected; it is not a statistical acceptance interval.
    """
    if t1 <= t0:
        raise ValueError("window must be positive")
    if boundary_safety_s <= 0:
        raise ValueError("declared boundary safety must be positive")
    samples = _sorted_samples(samples)
    _detect_unavailable_clock_evidence(samples)
    t0_lower, t0_upper = map_boundary(samples, t0)
    t1_lower, t1_upper = map_boundary(samples, t1)
    # The reported envelope includes declared safety and observed sampling
    # brackets. It is still not a guarantee about unsampled adjustment.
    # Basis: 1ms declared ordinary-step envelope for this same-host laptop,
    # matching the runner's 1-second decision/sampling grid. It is a
    # protocol constant, not estimated from outcomes; it does not cover
    # unseen steps and is not a statistical interval.
    lower, upper = t0_upper + boundary_safety_s, t1_lower - boundary_safety_s
    outer_lower, outer_upper = t0_lower - boundary_safety_s, t1_upper + boundary_safety_s
    # An envelope wider than the measured window makes strict inclusion
    # empty; that is an honest descriptive bound, not an invalid window.
    if lower > upper:
        strict_in = 0
    else:
        strict_in = sum(classify_frame(t, lower, upper) == "inside" for t in frame_epochs)
    possible_in = sum(classify_frame(t, outer_lower, outer_upper) == "inside" for t in frame_epochs)
    return {
        "strict_lower_bound_count": strict_in,
        "sampled_envelope_upper_bound_count": possible_in,
        "boundary_uncertain_count": possible_in - strict_in,
        "t0_sampled_epoch_interval_s": [t0_lower, t0_upper],
        "t1_sampled_epoch_interval_s": [t1_lower, t1_upper],
        "declared_boundary_safety_s": boundary_safety_s,
        "label": "conditional sampled-clock envelope; assumptions explicit; not guaranteed bounds on unseen clock behavior; no acceptance interval",
        "boundary_safety_basis": "1ms protocol constant aligned to runner 1s grid; not outcome-derived or a statistical interval",
    }


def _detect_unavailable_clock_evidence(samples):
    observed_steps = []
    for left, right in zip(samples, samples[1:]):
        epoch_delta = right["epoch_before_s"] - left["epoch_after_s"]
        mono_delta = right["monotonic_s"] - left["monotonic_s"]
        if mono_delta < 0:
            raise ValueError("monotonic clock moved backwards")
        # A large mismatch is evidence of a wall-clock step. Sampling does
        # not prove absence between points; this is detection, not guarantee.
        if abs(epoch_delta - mono_delta) > 0.005:
            observed_steps.append({"after": left["label"], "before": right["label"],
                                   "epoch_delta_minus_monotonic_delta_s": epoch_delta-mono_delta})
    if observed_steps:
        raise ValueError("observed wall-clock step/nonlinearity makes mapped timing unavailable")


def frame_epochs_from_pcap(path):
    raw = path.read_bytes()
    magic = raw[:4]
    endian = '<' if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
    if magic not in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'):
        raise ValueError('unsupported pcap magic')
    nano = magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
    pos = 24; epochs=[]
    while pos < len(raw):
        sec, frac, caplen, wirelen = struct.unpack_from(endian+'IIII', raw, pos)
        pos += 16 + caplen
        epochs.append(sec + frac/(1e9 if nano else 1e6))
    return epochs
