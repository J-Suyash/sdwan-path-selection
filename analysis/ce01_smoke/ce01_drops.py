import pathlib, re, sys
sys.path.insert(0, ".")
d = pathlib.Path("testbed/outputs/ce01-smoke/e00-r00")
text = (d / "backlog-series.log").read_text()

# split into timestamped blocks like parse_backlog_series
blocks = []
ts = None; cur = []
for line in text.splitlines():
    s = line.strip()
    try:
        v = float(s); is_ts = "." in s
    except ValueError:
        is_ts = False
    if is_ts:
        if ts is not None: blocks.append((ts, "\n".join(cur)))
        ts = v; cur = []
    else:
        cur.append(line)
if ts is not None: blocks.append((ts, "\n".join(cur)))

# per block: qdisc sections; capture name + Sent pkts + dropped
sec_re = re.compile(r"qdisc (\w+) \S+.*?(?:\n(?!qdisc).*)*?", re.S)
sent_re = re.compile(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+), overlimits (\d+)")
print("SAMPLES", len(blocks))
first = blocks[0][1]; last = blocks[-1][1]
for label, blk in (("FIRST", first), ("LAST", last)):
    print("==", label, "block ts", blocks[0][0] if label=="FIRST" else blocks[-1][0])
    for m in re.finditer(r"qdisc (\w+)[^\n]*\n Sent (\d+) bytes (\d+) pkt \(dropped (\d+), overlimits (\d+)", blk):
        print("  %-6s sent_pkt=%s dropped=%s overlimits=%s" % (m.group(1), m.group(3), m.group(4), m.group(5)))
# delta across run for netem
def netem_drop(blk):
    m = re.search(r"qdisc netem[^\n]*\n Sent \d+ bytes (\d+) pkt \(dropped (\d+)", blk)
    return (int(m.group(1)), int(m.group(2))) if m else None
d0 = netem_drop(first); d1 = netem_drop(last)
if d0 and d1:
    print("NETEM_DELTA sent=%d dropped=%d" % (d1[0]-d0[0], d1[1]-d0[1]))
print("QDISC_AFTER full:")
print((d / "qdisc_after.txt").read_text())
