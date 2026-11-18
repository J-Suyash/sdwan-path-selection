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


_BACKLOG_TOKEN = re.compile(r"backlog\s+(\d+(?:\.\d+)?)([A-Za-z])")
_TC_BACKLOG_UNITS = {"b": 1, "K": 1024, "M": 1024**2, "G": 1024**3}


def parse_qdisc_backlog_bytes(output: str) -> int:
    """Largest backlog across qdisc lines, in bytes.

    Unit convention (iproute2 sprint_size, lib/json_print_math.c; binary
    strings and the full retained corpus are consistent with it): K/M/G
    are 1024-based, and a suffix prints only when the byte count is within
    +/-15 bytes of a unit multiple ("241Kb" means 241*1024 +/- 15), with
    plain bytes otherwise - which is why larger non-multiples such as
    246630 print plain.  Suffixed forms therefore carry a +/-15-byte
    rounding window, not an exact value.  Unknown units or malformed
    backlog tokens raise instead of silently reading zero; output without
    any backlog token still yields 0.
    """
    values = []
    for digits, unit in _BACKLOG_TOKEN.findall(output):
        if unit not in _TC_BACKLOG_UNITS:
            raise ValueError(f"unknown tc backlog unit {unit!r}")
        values.append(int(float(digits) * _TC_BACKLOG_UNITS[unit]))
    if not values and "backlog" in output:
        raise ValueError("unparseable tc backlog token in qdisc output")
    return max(values, default=0)


def extract_packet_marks(pcap: Path) -> list[dict]:
    """Extract per-packet match marks from a pcap via tshark.

    Returns one dict per packet: ts (epoch float), proto ("tcp"/"udp"),
    ip_id, src_port, dst_port, length. Candidate instrumentation for
    cross-capture packet matching; parsing only, no validation implied.
    """
    if not pcap.exists() or pcap.stat().st_size == 0:
        return []
    output = subprocess.run(
        [
            "tshark",
            "-r",
            str(pcap),
            "-T",
            "fields",
            "-e",
            "frame.time_epoch",
            "-e",
            "ip.id",
            "-e",
            "frame.len",
            "-e",
            "tcp.srcport",
            "-e",
            "udp.srcport",
            "-e",
            "tcp.dstport",
            "-e",
            "udp.dstport",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    marks = []
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) != 7 or not fields[0] or not fields[1]:
            continue
        ts, ip_id, length = fields[0], fields[1], fields[2]
        src = fields[3] or fields[4]
        dst = fields[5] or fields[6]
        if not src or not dst:
            continue
        marks.append(
            {
                "ts": float(ts),
                "ip_id": int(ip_id, 16) if ip_id.startswith("0x") else int(ip_id),
                "proto": "tcp" if fields[3] else "udp",
                "src_port": int(src),
                "dst_port": int(dst),
                "length": int(length),
            }
        )
    return marks


def match_residence(
    pre_packets: list[dict],
    post_packets: list[dict],
    server_port: int,
    *,
    max_window_s: float = 2.0,
) -> dict:
    """Match forward packets between a pre-queue and a post-queue capture.

    Both captures must share one clock (they do: same host, kernel
    timestamps). A match is one-to-one on (proto, ip_id, length, src_port,
    dst_port) with the nearest post-queue timestamp at/after the pre-queue
    timestamp within max_window_s.

    HONEST SEMANTICS: the returned residence is full branch-side residence
    = queue wait + configured netem delay + per-packet jitter + OVS
    forwarding delay. It is NOT pure queue sojourn. For a sojourn estimate,
    subtract the path's configured one-way delay; per-packet jitter remains
    an unrecoverable confound bounded by the configured jitter.
    """
    from bisect import bisect_left
    from collections import defaultdict

    def forward(packets):
        return sorted(
            (p for p in packets if p["dst_port"] == server_port),
            key=lambda p: p["ts"],
        )

    pre = forward(pre_packets)
    post = forward(post_packets)
    buckets = defaultdict(list)
    for packet in post:
        key = (
            packet["proto"],
            packet["ip_id"],
            packet["length"],
            packet["src_port"],
            packet["dst_port"],
        )
        buckets[key].append(packet["ts"])
    residences = []
    unmatched_pre = 0
    for packet in pre:
        key = (
            packet["proto"],
            packet["ip_id"],
            packet["length"],
            packet["src_port"],
            packet["dst_port"],
        )
        candidates = buckets.get(key)
        if not candidates:
            unmatched_pre += 1
            continue
        index = bisect_left(candidates, packet["ts"] - 1e-3)
        if index >= len(candidates):
            unmatched_pre += 1
            continue
        delta = candidates[index] - packet["ts"]
        if delta > max_window_s:
            unmatched_pre += 1
            continue
        candidates.pop(index)
        residences.append(delta)
    unmatched_post = sum(len(v) for v in buckets.values())
    return {
        "residences_s": residences,
        "matched": len(residences),
        "unmatched_pre": unmatched_pre,
        "unmatched_post": unmatched_post,
    }


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
