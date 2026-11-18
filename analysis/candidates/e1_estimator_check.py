#!/usr/bin/env python3
"""E1 estimator-form characterization on the existing ce01 smoke data.

Compares candidate per-step aggregate delay forms against the measured
per-packet median delay, using only existing artifacts:
  prequeue.pcap  - sender-side tap (h1-eth0), epoch timestamps, all 75001 sent
  traffic.pcap   - receiver-side tap (server-eth0), epoch timestamps, 55608 recv
  backlog-series.log - 159 timestamped `tc -s qdisc` samples (epoch)
Both pcaps and the backlog log share the wall clock, so no cross-clock
alignment is estimated. This is characterization only: no estimator is
tuned here, and the aggregate forms are candidates, not ground truth.
"""
import json
import re
import statistics
import struct
import sys

BASE = "/home/sxtr/Projects/Major Project-instinct-recovery/testbed/outputs/ce01-smoke/e00-r00"
SAG_EPOCH = 1794987417.5760746  # metrics.json event_applied_epoch_s
RTT_MS = 75.0                   # metrics.json old/new_rtt_ms
BASE_MS = RTT_MS * 0.5          # emulator one-way factor (env/sdwan_env.py)
RATE_PRE = 150.0                # Mbps
RATE_POST = 30.0
HDR = struct.Struct("!Qd")      # traffic.py HEADER: seq, sent_at(monotonic)


def read_pcap_seq_ts(path):
    out = {}
    with open(path, "rb") as fh:
        magic = fh.read(4)
        rest = fh.read(20)
        if magic == b"\xd4\xc3\xb2\xa1":
            endian, scale = "<", 1e6
        elif magic == b"\xa1\xb2\xc3\xd4":
            endian, scale = ">", 1e6
        elif magic == b"\x4d\x3c\xb2\xa1":
            endian, scale = "<", 1e9
        elif magic == b"\xa1\xb2\x3c\x4d":
            endian, scale = ">", 1e9
        else:
            raise ValueError("bad magic " + magic.hex())
        while True:
            hdr = fh.read(16)
            if len(hdr) < 16:
                break
            ts_sec, ts_frac, incl, orig = struct.unpack(endian + "IIII", hdr)
            frame = fh.read(incl)
            if len(frame) < incl or incl < 42 + 16:
                continue
            ihl = (frame[14] & 0x0F) * 4
            proto = frame[14 + 9]
            if proto != 17:
                continue
            payload_off = 14 + ihl + 8
            if len(frame) < payload_off + HDR.size:
                continue
            seq, _sent_mono = HDR.unpack_from(frame[payload_off:])
            out[seq] = ts_sec + ts_frac / scale
    return out


def read_backlog(path):
    samples = []
    cur_ts = None
    section = None
    ts_re = re.compile(r"^(\d{10}\.\d+)")
    bl_re = re.compile(r"backlog (\d+)b (\d+)p")
    for line in open(path):
        m = ts_re.match(line)
        if m:
            cur_ts = float(m.group(1))
            samples.append({"ts": cur_ts})
            section = None
            continue
        if cur_ts is None:
            continue
        if line.startswith("qdisc tbf"):
            section = "tbf"
        elif line.startswith("qdisc netem"):
            section = "netem"
        else:
            b = bl_re.search(line)
            if b and section in ("tbf", "netem"):
                samples[-1][section + "_bytes"] = int(b.group(1))
                samples[-1][section + "_pkts"] = int(b.group(2))
    return [s for s in samples if "tbf_bytes" in s or "netem_bytes" in s]


def backlog_at(samples, ts, key):
    val = 0
    for s in samples:
        if s["ts"] <= ts:
            val = s.get(key, 0)
        else:
            break
    return val


def service_bytes_per_s(ts):
    return (RATE_PRE if ts < SAG_EPOCH else RATE_POST) * 1e6 / 8.0


def agg_delay_ms(samples, ts, form):
    tbf = backlog_at(samples, ts, "tbf_bytes")
    netem = backlog_at(samples, ts, "netem_bytes")
    svc = service_bytes_per_s(ts)
    if form == "A_double_count":
        return BASE_MS + (tbf + netem) / svc * 1000.0
    if form == "B_rate_queue_only":
        return BASE_MS + tbf / svc * 1000.0
    if form == "C_netem_only":
        return BASE_MS + netem / svc * 1000.0
    raise ValueError(form)


def main():
    sent = read_pcap_seq_ts(BASE + "/prequeue.pcap")
    recv = read_pcap_seq_ts(BASE + "/traffic.pcap")
    samples = read_backlog(BASE + "/backlog-series.log")
    samples.sort(key=lambda s: s["ts"])

    common = sorted(set(sent) & set(recv))
    delays = {s: (recv[s] - sent[s]) * 1000.0 for s in common}
    first_send = min(sent.values())
    last_recv = max(recv.values())

    dts = [b["ts"] - a["ts"] for a, b in zip(samples, samples[1:])]
    print("sampling: n=%d mean_dt=%.3fs median_dt=%.3fs min=%.3f max=%.3f"
          % (len(samples), statistics.fmean(dts), statistics.median(dts),
             min(dts), max(dts)))
    print("run window: first_send=%.6f last_recv=%.6f span=%.2fs"
          % (first_send, last_recv, last_recv - first_send))

    def packet_median(lo, hi):
        sel = [d for s, d in delays.items() if lo <= sent[s] < hi]
        return (statistics.median(sel), len(sel)) if sel else (float("nan"), 0)

    windows = {
        "full": (first_send, last_recv),
        "pre_sag": (first_send, SAG_EPOCH),
        "post_sag": (SAG_EPOCH, last_recv),
        "pre_sag_2s": (SAG_EPOCH - 2.0, SAG_EPOCH),
        "post_sag_2s": (SAG_EPOCH, SAG_EPOCH + 2.0),
        "post_sag_5s": (SAG_EPOCH, SAG_EPOCH + 5.0),
    }
    print("pipeline check vs metrics.json delay_median_ms=38.317077996907756:")
    med_full, n_full = packet_median(*windows["full"])
    print("  parsed full-run per-packet median=%.6f ms over n=%d packets"
          % (med_full, n_full))

    results = {}
    step = 1.0
    for wname, (lo, hi) in windows.items():
        pmed, npk = packet_median(lo, hi)
        row = {"packet_median_ms": pmed, "n_packets": npk, "forms": {}}
        for form in ("A_double_count", "B_rate_queue_only", "C_netem_only"):
            for phase in (0.0, 0.25, 0.5, 0.75):
                # time-weighted: median over grid points
                t = lo + phase
                vals = []
                while t < hi:
                    vals.append(agg_delay_ms(samples, t, form))
                    t += step
                tw = statistics.median(vals) if vals else float("nan")
                # packet-weighted: sample form at each send time
                pw_vals = [agg_delay_ms(samples, sent[s], form)
                           for s in common if lo <= sent[s] < hi]
                pw = statistics.median(pw_vals) if pw_vals else float("nan")
                row["forms"]["%s phase=%.2f" % (form, phase)] = {
                    "time_weighted_median_ms": tw,
                    "packet_weighted_median_ms": pw,
                }
        results[wname] = row

    for wname, row in results.items():
        print("\nwindow %s: per-packet median=%.3f ms (n=%d)"
              % (wname, row["packet_median_ms"], row["n_packets"]))
        for label, vals in row["forms"].items():
            print("  %-28s time-w=%8.3f ms  packet-w=%8.3f ms"
                  % (label, vals["time_weighted_median_ms"],
                     vals["packet_weighted_median_ms"]))

    # delay-line sanity: netem backlog vs base-delay bytes in flight
    post = [s for s in samples if s["ts"] > SAG_EPOCH + 1.0]
    if post:
        nb = statistics.fmean(s.get("netem_bytes", 0) for s in post)
        tb = statistics.fmean(s.get("tbf_bytes", 0) for s in post)
        svc_post = RATE_POST * 1e6 / 8.0
        print("\npost-sag means: netem_backlog=%.0f B (delay-line bytes at "
              "rate %.1f MB/s = %.1f ms) tbf_backlog=%.0f B (= %.1f ms at "
              "post-sag service)"
              % (nb, svc_post, nb / svc_post * 1000.0, tb,
                 tb / svc_post * 1000.0))


if __name__ == "__main__":
    main()
