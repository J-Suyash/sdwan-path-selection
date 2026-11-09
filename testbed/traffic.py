"""Timestamped UDP/TCP traffic generator used by switch experiments."""

from __future__ import annotations

import argparse
import csv
import socket
import struct
import time
from pathlib import Path

HEADER = struct.Struct("!Qd")


def write_event(
    writer: csv.writer, seq: int, sent_at: float, received_at: float
) -> None:
    writer.writerow((seq, f"{sent_at:.9f}", f"{received_at:.9f}"))


def run_udp_receiver(args: argparse.Namespace) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    sock.bind((args.bind, args.port))
    sock.settimeout(args.idle_timeout)
    deadline = time.monotonic() + args.timeout
    last_packet_at = time.monotonic()
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("seq", "sent_at", "received_at"))
        while (
            time.monotonic() < deadline
            and time.monotonic() - last_packet_at < args.idle_timeout
        ):
            try:
                packet, _ = sock.recvfrom(65535)
            except TimeoutError:
                continue
            if len(packet) < HEADER.size:
                continue
            seq, sent_at = HEADER.unpack_from(packet)
            last_packet_at = time.monotonic()
            write_event(writer, seq, sent_at, last_packet_at)


def run_udp_sender(args: argparse.Namespace) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b"\0" * max(0, args.packet_bytes - HEADER.size)
    interval_s = (args.packet_bytes * 8.0) / (args.rate_mbps * 1e6)
    start = time.monotonic()
    deadline = start + args.duration
    seq = 0
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("seq", "sent_at", "received_at"))
        while time.monotonic() < deadline:
            target = start + seq * interval_s
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
            sent_at = time.monotonic()
            packet = HEADER.pack(seq, sent_at) + payload
            sock.sendto(packet, (args.host, args.port))
            writer.writerow((seq, f"{sent_at:.9f}", f"{sent_at:.9f}"))
            seq += 1


def run_tcp_receiver(args: argparse.Namespace) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.listen(1)
    sock.settimeout(args.timeout)
    connection, _ = sock.accept()
    connection.settimeout(args.idle_timeout)
    buffer = bytearray()
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("seq", "sent_at", "received_at"))
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                data = connection.recv(65536)
            except TimeoutError:
                continue
            if not data:
                break
            received_at = time.monotonic()
            buffer.extend(data)
            while len(buffer) >= args.packet_bytes:
                packet = bytes(buffer[: args.packet_bytes])
                del buffer[: args.packet_bytes]
                seq, sent_at = HEADER.unpack_from(packet)
                write_event(writer, seq, sent_at, received_at)
    connection.close()
    sock.close()


def run_tcp_sender(args: argparse.Namespace) -> None:
    interval_s = (args.packet_bytes * 8.0) / (args.rate_mbps * 1e6)
    payload = b"\0" * max(0, args.packet_bytes - HEADER.size)
    deadline = time.monotonic() + args.timeout
    sock = None
    while sock is None and time.monotonic() < deadline:
        try:
            sock = socket.create_connection((args.host, args.port), timeout=1.0)
        except OSError:
            time.sleep(0.1)
    if sock is None:
        raise TimeoutError(f"could not connect to {args.host}:{args.port}")

    start = time.monotonic()
    deadline = start + args.duration
    seq = 0
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("seq", "sent_at", "received_at"))
        while time.monotonic() < deadline:
            target = start + seq * interval_s
            now = time.monotonic()
            if target > now:
                time.sleep(target - now)
            sent_at = time.monotonic()
            sock.sendall(HEADER.pack(seq, sent_at) + payload)
            writer.writerow((seq, f"{sent_at:.9f}", f"{sent_at:.9f}"))
            seq += 1
    sock.shutdown(socket.SHUT_WR)
    sock.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=["receiver", "sender"])
    parser.add_argument("transport", choices=["udp", "tcp"])
    parser.add_argument("--host", default="10.0.0.100")
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--rate-mbps", type=float, default=1.0)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--idle-timeout", type=float, default=2.0)
    parser.add_argument("--packet-bytes", type=int, default=1200)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.packet_bytes < HEADER.size:
        raise ValueError("--packet-bytes is smaller than the timestamp header")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    handler = globals()[f"run_{args.transport}_{args.role}"]
    handler(args)


if __name__ == "__main__":
    main()
