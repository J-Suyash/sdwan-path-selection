import json, pathlib, sys
sys.path.insert(0, ".")
from testbed.analyze import parse_backlog_series, extract_packet_marks, match_residence

d = pathlib.Path("testbed/outputs/ce01-smoke/e00-r00")
metrics = json.loads((d / "metrics.json").read_text())
ev = metrics["event_applied_epoch_s"]

series = parse_backlog_series((d / "backlog-series.log").read_text())
pre = [b for t, b in series if t < ev]
post = [b for t, b in series if t >= ev]
print("SAMPLES total=%d pre=%d post=%d" % (len(series), len(pre), len(post)))
print("EVENT_EPOCH", ev)
if series:
    print("TSPAN %.3f..%.3f" % (series[0][0], series[-1][0]))
def stats(xs):
    if not xs: return "none"
    xs = sorted(xs)
    return "min=%d med=%d max=%d" % (xs[0], xs[len(xs)//2], xs[-1])
print("BACKLOG_PRE  bytes:", stats(pre))
print("BACKLOG_POST bytes:", stats(post))

qb = (d / "qdisc_before.txt").read_text()
qa = (d / "qdisc_after.txt").read_text()
from testbed.analyze import parse_qdisc_backlog_bytes
print("QDISC_BEFORE_BACKLOG_BYTES", parse_qdisc_backlog_bytes(qb))
print("QDISC_AFTER_BACKLOG_BYTES", parse_qdisc_backlog_bytes(qa))
print("QDISC_AFTER_HEAD", qa.splitlines()[0][:120] if qa else "")

preq = extract_packet_marks(d / "prequeue.pcap")
postq = extract_packet_marks(d / "postqueue.pcap")
print("MARKS pre=%d post=%d" % (len(preq), len(postq)))
res = match_residence(preq, postq, 9999)
r = res.pop("residences_s")
n = len(r)
if n:
    r_sorted = sorted(r)
    print("RESIDENCE_S n=%d min=%.4f med=%.4f p95=%.4f max=%.4f" % (
        n, r_sorted[0], r_sorted[n//2], r_sorted[int(n*0.95)], r_sorted[-1]))
print("MATCHER", json.dumps(res, sort_keys=True))
