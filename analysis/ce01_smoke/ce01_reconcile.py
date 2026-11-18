import json, pathlib, sys
sys.path.insert(0, ".")
from testbed.analyze import extract_packet_marks, match_residence

d = pathlib.Path("testbed/outputs/ce01-smoke/e00-r00")
def load(path):
    rows = {}
    for i, line in enumerate(path.read_text().splitlines()):
        if i == 0: continue
        seq, a, b = line.split(",")
        rows[int(seq)] = (float(a), float(b))
    return rows
sent = load(d / "sender.csv")
recv = load(d / "receiver.csv")
missing = sorted(set(sent) - set(recv))
print("SENT", len(sent), "RECV", len(recv), "MISSING", len(missing))
if missing:
    msent = [sent[s][0] for s in missing]
    print("MISSING_SEQ min=%d max=%d" % (missing[0], missing[-1]))
    print("MISSING_SENT_AT min=%.3f max=%.3f" % (msent[0], msent[-1]))
    allsent = sorted(v[0] for v in sent.values())
    print("ALL_SENT_AT  min=%.3f max=%.3f" % (allsent[0], allsent[-1]))
    # contiguous tail?
    tail = set(range(missing[-1] - len(missing) + 1, missing[-1] + 1))
    print("MISSING_IS_CONTIGUOUS_TAIL", set(missing) == tail)
    first_sent_of_missing = msent[0]
    total_span = allsent[-1] - allsent[0]
    print("FIRST_MISSING_AT_FRACTION_OF_RUN %.4f" % ((first_sent_of_missing - allsent[0]) / total_span))
# last received vs sender end
rrecv = sorted(v[1] for v in recv.values())
print("LAST_RECV_AT %.3f  SENDER_END %.3f  GAP %.3f s" % (rrecv[-1], allsent[-1], rrecv[-1] - allsent[-1]))

# full-precision residence stats
preq = extract_packet_marks(d / "prequeue.pcap")
postq = extract_packet_marks(d / "postqueue.pcap")
res = match_residence(preq, postq, 9999)
r = sorted(res["residences_s"])
n = len(r)
def pct(xs, q):
    import statistics
    # match analyze._percentile behavior (linear interpolation)
    if not xs: return None
    k = (len(xs) - 1) * q
    f = int(k); c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)
print("RESIDENCE_MEDIAN_MS %.9f" % (pct(r, 0.5) * 1000))
print("RESIDENCE_P95_MS %.9f" % (pct(r, 0.95) * 1000))
m = json.loads((d / "metrics.json").read_text())
print("TRAFFIC_DELAY_MEDIAN_MS %.9f" % m["delay_median_ms"])
print("TRAFFIC_DELAY_P95_MS %.9f" % m["delay_p95_ms"])
