from pathlib import Path

import pytest

from testbed.analyze import (
    parse_qdisc_backlog_bytes,
    summarize_traffic,
)


def _write_log(path: Path, rows: list[tuple[int, float, float]]) -> None:
    lines = ["seq,sent_at,received_at"]
    lines.extend(f"{seq},{sent:.9f},{received:.9f}" for seq, sent, received in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_traffic_summary_detects_loss_gap_and_reordering(tmp_path):
    sender = tmp_path / "sender.csv"
    receiver = tmp_path / "receiver.csv"
    _write_log(
        sender,
        [
            (0, 10.00, 10.00),
            (1, 10.01, 10.01),
            (2, 10.02, 10.02),
            (3, 10.03, 10.03),
            (4, 10.04, 10.04),
        ],
    )
    _write_log(
        receiver,
        [
            (0, 10.00, 10.03),
            (1, 10.01, 10.04),
            (3, 10.03, 10.09),
            (4, 10.04, 10.10),
        ],
    )

    result = summarize_traffic(
        sender,
        receiver,
        packet_bytes=1200,
        switch_at_s=10.055,
    )

    assert result["loss_frac"] == pytest.approx(0.2)
    assert result["interruption_s"] > 0.04
    assert result["delay_median_ms"] == pytest.approx(45.0)
    assert result["jitter_mean_ms"] == pytest.approx(10.0)


def test_udp_reordering_is_counted(monkeypatch):
    import testbed.analyze as module

    values = {0: 1.0, 2: 1.2, 1: 1.3}
    monkeypatch.setattr(module, "_read_events", lambda path: values)
    result = module.summarize_traffic(
        Path("sender.csv"),
        Path("receiver.csv"),
        packet_bytes=1000,
        switch_at_s=1.1,
    )
    assert result["reordering_frac"] == pytest.approx(1 / 3)


def test_qdisc_backlog_uses_largest_observed_queue():
    output = """
qdisc netem 10: root refcnt 2 limit 1000
 Sent 1000 bytes 10 pkt (dropped 0, overlimits 0 requeues 0)
 backlog 12500b 8p requeues 0
qdisc tbf 5: parent 10:1 limit 100000b
 backlog 250b 1p requeues 0
"""
    assert parse_qdisc_backlog_bytes(output) == 12_500
def test_qdisc_backlog_parses_tc_suffix_units():
    # tc prints a suffix only on exact multiples; suffixed values are exact.
    assert parse_qdisc_backlog_bytes(" backlog 241Kb 163p requeues 0\n") == 241 * 1024
    assert parse_qdisc_backlog_bytes(" backlog 2Mb 100p requeues 0\n") == 2 * 1024**2
    assert parse_qdisc_backlog_bytes(" backlog 1Gb 100p requeues 0\n") == 1024**3
    assert parse_qdisc_backlog_bytes(" backlog 1.5Kb 10p requeues 0\n") == 1536


def test_qdisc_backlog_mixed_units_take_max():
    output = """
qdisc tbf 5: root
 backlog 97770b 65p requeues 0
qdisc netem 10: parent 5:1
 backlog 94Kb 65p requeues 0
"""
    assert parse_qdisc_backlog_bytes(output) == 97770


def test_qdisc_backlog_zero_and_absent():
    assert parse_qdisc_backlog_bytes(" backlog 0b 0p requeues 0\n") == 0
    assert parse_qdisc_backlog_bytes("qdisc netem 10: root\n Sent 0 bytes 0 pkt\n") == 0


def test_qdisc_backlog_rejects_unknown_unit():
    with pytest.raises(ValueError, match="unknown tc backlog unit"):
        parse_qdisc_backlog_bytes(" backlog 12Tb 3p requeues 0\n")


def test_qdisc_backlog_rejects_malformed_token():
    with pytest.raises(ValueError, match="unparseable tc backlog token"):
        parse_qdisc_backlog_bytes(" backlog notanumber requeues 0\n")
