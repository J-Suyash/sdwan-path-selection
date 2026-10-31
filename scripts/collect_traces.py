"""Continuous link trace collector (proposal Section 11.3).

Pings a fixed target every --ping-interval seconds (default 0.2) and,
when iperf3 is available, runs a --iperf-duration second throughput test
every --iperf-interval seconds (default 600). Appends rows to a CSV with
UTC timestamps.

CSV columns: ts_epoch_ms, label, kind, seq, rtt_ms, bps
  kind=ping  : one row per ping reply; rtt_ms from the reply, bps empty
  kind=iperf : one row per throughput test; rtt_ms empty, bps in Mbps
  kind=meta  : startup notes (e.g. iperf3 missing)

Example:
    python3 collect_traces.py --target bigguy --label broadband \
        --out traces_broadband.csv
"""

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time


PING_RE = re.compile(
    r"icmp_seq=(?P<seq>\d+).*time=(?P<rtt>[\d.]+) ms", re.IGNORECASE
)


class Writer:
    """Thread-safe CSV appender."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.lock = threading.Lock()
        new_file = not os.path.exists(path) or os.path.getsize(path) == 0
        with self.lock, open(path, "a", newline="") as f:
            if new_file:
                csv.writer(f).writerow(
                    ["ts_epoch_ms", "label", "kind", "seq", "rtt_ms", "bps"]
                )

    def row(self, label: str, kind: str, seq: str = "", rtt: str = "", bps: str = "") -> None:
        with self.lock, open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(
                [int(time.time() * 1000), label, kind, seq, rtt, bps]
            )
            f.flush()


def iperf_loop(writer: Writer, args: argparse.Namespace, iperf: str) -> None:
    time.sleep(min(args.iperf_interval, 300))
    while True:
        try:
            iperf_target = args.iperf_target or args.target
            proc = subprocess.run(
                [iperf, "-c", iperf_target, "-t", str(args.iperf_duration), "-J"],
                capture_output=True,
                text=True,
                timeout=args.iperf_duration + 30,
            )
            if proc.returncode != 0:
                writer.row(args.label, "iperf", bps="")
                continue
            data = json.loads(proc.stdout)
            bps = data["end"]["sum_received"]["bits_per_second"]
            writer.row(args.label, "iperf", bps=f"{bps / 1e6:.3f}")
        except Exception:
            writer.row(args.label, "iperf", bps="")
        time.sleep(max(args.iperf_interval - args.iperf_duration, 60))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ping-interval", type=float, default=0.2)
    ap.add_argument("--iperf-interval", type=int, default=600)
    ap.add_argument("--iperf-duration", type=int, default=10)
    ap.add_argument(
        "--iperf-target",
        default=None,
        help="iperf3 server address; defaults to --target",
    )
    args = ap.parse_args()

    ping = shutil.which("ping")
    iperf = shutil.which("iperf3")
    if not ping:
        sys.exit("ping not found")

    writer = Writer(args.out)
    writer.row(args.label, "meta", bps=f"start target={args.target} ping_interval={args.ping_interval}")
    if iperf:
        writer.row(args.label, "meta", bps=f"iperf3={iperf}")
        threading.Thread(target=iperf_loop, args=(writer, args, iperf), daemon=True).start()
    else:
        writer.row(args.label, "meta", bps="iperf3 missing; ping only")

    proc = subprocess.Popen(
        [ping, "-n", "-i", str(args.ping_interval), args.target],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        match = PING_RE.search(line)
        if match:
            writer.row(
                args.label,
                "ping",
                seq=match.group("seq"),
                rtt=match.group("rtt"),
            )


if __name__ == "__main__":
    main()
