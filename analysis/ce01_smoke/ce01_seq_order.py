"""Sequence-order analysis for the ce01 smoke captures (one-off diagnostic).

Parses the application-layer sequence number (struct '!Qd' header written by
testbed/traffic.py) from the pre-queue and post-queue pcaps in capture-file
order and reports inversion counts, with validation of the extraction
itself: pcap timestamp monotonicity, decode set-equality with sender.csv,
duplicate and wrap checks, and divergence against receiver.csv order.

Interpretation boundary: this reports OBSERVED CAPTURE-SEQUENCE order at
each tap and in the application log. It does not by itself establish
physical wire reorder or attribute a platform mechanism.

Run from the repo root: python3 analysis/ce01_smoke/ce01_seq_order.py
"""

import pathlib
import re
import struct
import subprocess

H = struct.Struct("!Qd")
RUN_DIR = pathlib.Path("testbed/outputs/ce01-smoke/e00-r00")


def capture_seqs(pcap: pathlib.Path):
    """(pcap_ts, seq) per captured UDP frame to dst port 9999, in file order."""
    out = subprocess.run(
        ["tcpdump", "-r", str(pcap), "-nn", "-tt", "-xx", "udp", "and", "dst", "port", "9999"],
        capture_output=True, text=True,
    ).stdout
    frames, cur_hex, cur_ts = [], [], None
    for line in out.splitlines():
        m = re.match(r"^(\d+\.\d+)\s", line)  # requires -tt epoch timestamps
        if m:
            if cur_hex and cur_ts is not None:
                payload = bytes.fromhex("".join(cur_hex))
                if len(payload) >= 42 + H.size:
                    frames.append((cur_ts, H.unpack_from(payload, 42)[0]))
            cur_hex, cur_ts = [], float(m.group(1))
        elif line.startswith("\t0x"):
            cur_hex.append("".join(line.split(":", 1)[1].split()))
    if cur_hex and cur_ts is not None:
        payload = bytes.fromhex("".join(cur_hex))
        if len(payload) >= 42 + H.size:
            frames.append((cur_ts, H.unpack_from(payload, 42)[0]))
    return frames


def inversions(seqs):
    return sum(1 for a, b in zip(seqs, seqs[1:]) if b < a)


def main() -> None:
    pre = capture_seqs(RUN_DIR / "prequeue.pcap")
    post = capture_seqs(RUN_DIR / "postqueue.pcap")
    pre_seqs = [s for _, s in pre]
    post_seqs = [s for _, s in post]

    # --- extraction validation ---
    print("TS_MONOTONE_PRE", all(b[0] >= a[0] for a, b in zip(pre, pre[1:])))
    print("TS_MONOTONE_POST", all(b[0] >= a[0] for a, b in zip(post, post[1:])))
    sender = {int(l.split(",")[0])
              for l in (RUN_DIR / "sender.csv").read_text().splitlines()[1:]}
    print("PRE_SET_EQ_SENDER", set(pre_seqs) == sender)
    print("PRE_DUPS", len(pre_seqs) - len(set(pre_seqs)),
          "POST_DUPS", len(post_seqs) - len(set(post_seqs)))
    print("SEQ_RANGE", min(sender), max(sender), "(uint64: no wrap possible)")

    # --- observed capture-sequence inversions ---
    print("PRE_INV", inversions(pre_seqs))
    print("POST_INV", inversions(post_seqs))
    neg = [b - a for a, b in zip(post_seqs, post_seqs[1:]) if b < a]
    print("POST_NEG_STEPS", len(neg), "MOST_NEGATIVE", min(neg) if neg else None)

    # --- divergence between post-tap order and application log order ---
    recv = [int(l.split(",")[0])
            for l in (RUN_DIR / "receiver.csv").read_text().splitlines()[1:]]
    missing = set(post_seqs) - set(recv)
    filtered = [s for s in post_seqs if s not in missing]
    mism = sum(1 for a, b in zip(filtered, recv) if a != b)
    print("RECV_N", len(recv), "MISSING_FROM_APP", len(missing),
          "RECV_DUP_ROWS", len(recv) - len(set(recv)))
    print("INV_RECV", inversions(recv), "INV_FILTERED_POST", inversions(filtered))
    print("POSITION_MISMATCHES", mism, "OF", len(recv))


if __name__ == "__main__":
    main()
