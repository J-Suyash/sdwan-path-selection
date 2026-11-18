"""Pure parser tests for the backlog-sampler log format."""

from testbed.analyze import parse_backlog_series


SAMPLE = """1769000000.000001000
qdisc tbf 5: root refcnt 2 rate 150Mbit burst 15000b lat 0.8ms
 Sent 1000 bytes 10 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc netem 10: parent 5:1 limit 3125 delay 37.5ms  1.0ms
 Sent 1000 bytes 10 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 241Kb 200p requeues 0
1769000000.100002000
qdisc tbf 5: root refcnt 2 rate 150Mbit burst 15000b lat 0.8ms
 Sent 2000 bytes 20 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
qdisc netem 10: parent 5:1 limit 3125 delay 37.5ms  1.0ms
 Sent 2000 bytes 20 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 0b 0p requeues 0
"""


def test_parses_timestamped_blocks():
    series = parse_backlog_series(SAMPLE)
    assert len(series) == 2
    assert series[0][0] == 1769000000.000001
    # largest backlog across sections: 241Kb = 241*1024
    assert series[0][1] == 241 * 1024
    # zero backlog block parses as zero
    assert series[1][1] == 0


def test_empty_log():
    assert parse_backlog_series("") == []


def test_trailing_block_without_samples_still_emits():
    series = parse_backlog_series("1769000000.5\nqdisc netem 10: root\n backlog 100b 1p\n")
    assert series == [(1769000000.5, 100)]
