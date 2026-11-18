"""FLAGGED CANDIDATE: queue-delay-like proxy from two-point captures.

NOT an accepted metric. The output name is ``queue_delay_proxy_ms`` and
must never be emitted as ``queue_delay_ms`` or fed to an acceptance gate.

Definition (candidate): per matched packet,
    proxy = residence_s - configured_base_delay_s
where residence_s is pre-queue-tap tx to post-queue-tap rx from
testbed.analyze.match_residence, and configured_base_delay_s is the netem
base delay configured for the path (NOT including jitter).

Known negatives and uncertainty (each is a reason this stays a proxy):

1. Delay-line/backlog sharing: in the ce01 smoke the netem delay line shares
   the 3125-packet limit, so configured delay elapses while the backlog ahead
   drains. Subtracting the full base delay can therefore remove part of the
   actual wait during saturation; the proxy can UNDERSTATE queueing delay in
   exactly the regime ce01 studies. The observed ~0.6 ms agreement was total
   drain time vs residence p95 - it does not validate the subtraction.
2. Residence includes more than queue+delay: the netem jitter realization
   (uniform +/-jitter around base), the OVS/veth forwarding path, and tap
   placement offsets all sit inside the measured residence. None are
   separated here.
3. Negative proxies are possible (residence < base when the jitter draw is
   negative): they are reported as a count, not clamped away, because their
   frequency is itself an uncertainty indicator.
4. No equivalence is established with the emulator's fluid queue quantity
   (env/queue.py tracks occupancy_bytes; a fluid service-wait analogue would
   be occupancy/service-rate - a drain estimate with its own caveats).

Run from the repo root. Diagnostic use only.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, ".")

from testbed.analyze import extract_packet_marks, match_residence

PROXY_LABEL = "queue_delay_proxy_ms_UNVALIDATED_CANDIDATE"


def queue_delay_proxy(residences_s, configured_base_delay_s: float) -> dict:
    """Proxy stats from a residence series. See module docstring."""
    proxies = [r - configured_base_delay_s for r in residences_s]
    negatives = sum(1 for p in proxies if p < 0.0)
    out = {
        "metric_name": PROXY_LABEL,
        "n": len(proxies),
        "negative_count": negatives,
        "caveats": [
            "delay-line/backlog sharing: proxy can understate wait in saturation",
            "residence includes jitter draw, OVS/veth path and tap placement",
            "drain-vs-residence agreement is not validation of the subtraction",
            "no equivalence with emulator fluid queue quantity established",
        ],
    }
    if proxies:
        s = sorted(proxies)
        n = len(s)
        out["median_ms"] = s[n // 2] * 1e3
        out["p95_ms"] = s[int(n * 0.95)] * 1e3
        out["max_ms"] = s[-1] * 1e3
    return out


def from_captures(run_dir: str, configured_base_delay_s: float, port: int = 9999) -> dict:
    d = pathlib.Path(run_dir)
    pre = extract_packet_marks(d / "prequeue.pcap")
    post = extract_packet_marks(d / "postqueue.pcap")
    res = match_residence(pre, post, port)
    return queue_delay_proxy(res["residences_s"], configured_base_delay_s)


if __name__ == "__main__":
    import json

    result = from_captures("testbed/outputs/ce01-smoke/e00-r00", 37.5e-3)
    print(json.dumps(result, indent=2, sort_keys=True))
