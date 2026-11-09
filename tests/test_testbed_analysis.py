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
