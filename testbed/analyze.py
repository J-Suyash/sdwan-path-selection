"""Parse testbed traffic logs and PCAP counters into calibration metrics."""

from __future__ import annotations

import csv
import re
import subprocess
from itertools import pairwise
from pathlib import Path
from statistics import fmean


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    fraction = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * fraction


def _read_events(path: Path) -> dict[int, float]:
    events: dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            events[int(row["seq"])] = float(row["received_at"])
    return events


def summarize_traffic(
    sender_log: Path,
    receiver_log: Path,
    *,
    packet_bytes: int,
    switch_at_s: float,
) -> dict[str, float | int]:
    sent = _read_events(sender_log)
    received = _read_events(receiver_log)
    # Preserve receiver log order.  Sequence order is useful for matching
    # timestamps, but sorting by sequence number erases the evidence needed
    # to detect packets that arrived out of order.
    matched = [
        (seq, received_at) for seq, received_at in received.items() if seq in sent
    ]
    if not sent:
        raise ValueError(f"no sent events in {sender_log}")

    received_count = len(matched)
    loss_frac = max(0.0, 1.0 - received_count / len(sent))
    arrivals = [received_at for _, received_at in matched]
    interarrival = [right - left for left, right in pairwise(arrivals)]
    nominal_gap = _percentile(interarrival, 0.5) if interarrival else 0.0
    max_gap = max(interarrival, default=0.0)
    interruption_s = max(0.0, max_gap - nominal_gap)

    max_seen = -1
    reordered = 0
    for seq, _ in matched:
        if seq < max_seen:
            reordered += 1
        max_seen = max(max_seen, seq)
    reordering_frac = reordered / received_count if received_count else 0.0

    delays_ms = [(received_at - sent[seq]) * 1000.0 for seq, received_at in matched]
    duration_s = max(arrivals) - min(arrivals) if len(arrivals) > 1 else 0.0
    throughput_mbps = (
        received_count * packet_bytes * 8.0 / duration_s / 1e6
        if duration_s > 0
        else 0.0
    )
    switch_received = [
        received_at
        for _, received_at in matched
        if abs(received_at - switch_at_s) <= 1.5
    ]
    return {
        "sent_frames": len(sent),
        "received_frames": received_count,
        "loss_frac": loss_frac,
        "interruption_s": interruption_s,
        "reordering_frac": reordering_frac,
        "delay_median_ms": _percentile(delays_ms, 0.5),
        "delay_p95_ms": _percentile(delays_ms, 0.95),
        "jitter_mean_ms": (
            fmean(abs(right - left) for left, right in pairwise(delays_ms))
            if len(delays_ms) > 1
            else 0.0
        ),
        "throughput_mbps": throughput_mbps,
        "received_near_switch": len(switch_received),
    }


def parse_qdisc_backlog_bytes(output: str) -> int:
    matches = re.findall(r"backlog\s+(\d+)b", output)
    return max((int(value) for value in matches), default=0)


def summarize_pcap(pcap: Path) -> dict[str, int]:
    if not pcap.exists() or pcap.stat().st_size == 0:
        return {
            "tcp_data_packets": 0,
            "tcp_retransmissions": 0,
            "tcp_out_of_order": 0,
        }

    def count(display_filter: str) -> int:
        output = subprocess.run(
            [
                "tshark",
                "-r",
                str(pcap),
                "-Y",
                display_filter,
                "-T",
                "fields",
                "-e",
                "frame.number",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        return len([line for line in output.splitlines() if line.strip()])

    return {
        "tcp_data_packets": count("tcp.len > 0"),
        "tcp_retransmissions": count("tcp.analysis.retransmission"),
        "tcp_out_of_order": count("tcp.analysis.out_of_order"),
    }
