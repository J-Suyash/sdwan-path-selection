"""Pure matching tests for queue-residence instrumentation (no tshark/pcap)."""

from testbed.analyze import match_residence


def pkt(ts, ip_id, src, dst, length=1400, proto="udp"):
    return {"ts": ts, "ip_id": ip_id, "proto": proto,
            "src_port": src, "dst_port": dst, "length": length}


def test_forward_pairs_matched_with_residence():
    pre = [pkt(10.0, 1, 40000, 9999), pkt(10.5, 2, 40000, 9999)]
    post = [pkt(10.120, 1, 40000, 9999), pkt(10.660, 2, 40000, 9999)]
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 2
    assert abs(result["residences_s"][0] - 0.120) < 1e-9
    assert abs(result["residences_s"][1] - 0.160) < 1e-9
    assert result["unmatched_pre"] == 0
    assert result["unmatched_post"] == 0


def test_reverse_direction_packets_ignored():
    pre = [pkt(10.0, 1, 9999, 40000)]  # server->client, not forward
    post = [pkt(10.1, 1, 9999, 40000)]
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 0
    assert result["unmatched_pre"] == 0
    assert result["unmatched_post"] == 0


def test_duplicate_keys_match_one_to_one():
    # identical keys cannot be disambiguated; the documented policy is
    # greedy in pre-queue order, nearest post timestamp at/after the pre
    pre = [pkt(10.0, 7, 40000, 9999), pkt(10.2, 7, 40000, 9999)]
    post = [pkt(10.3, 7, 40000, 9999)]
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 1
    assert result["unmatched_pre"] == 1
    assert abs(result["residences_s"][0] - 0.3) < 1e-9


def test_window_excludes_stale_candidates():
    pre = [pkt(10.0, 1, 40000, 9999)]
    post = [pkt(15.0, 1, 40000, 9999)]  # 5s later, beyond 2s window
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 0
    assert result["unmatched_pre"] == 0
    assert result["beyond_window"] == 1  # tail-censored, counted separately
    assert result["unmatched_post"] == 1


def test_ambiguity_flagged_not_silently_trusted():
    # two post candidates inside the window for one pre packet
    pre = [pkt(10.0, 1, 40000, 9999)]
    post = [pkt(10.1, 1, 40000, 9999), pkt(10.2, 1, 40000, 9999)]
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 1
    assert result["ambiguous_matches"] == 1


def test_duplicate_pre_keys_counted():
    pre = [pkt(10.0, 1, 40000, 9999), pkt(10.1, 1, 40000, 9999)]
    post = [pkt(10.15, 1, 40000, 9999), pkt(10.25, 1, 40000, 9999)]
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 2
    assert result["duplicate_pre_keys"] == 1


def test_post_timestamp_must_be_at_or_after_pre():
    pre = [pkt(10.0, 1, 40000, 9999)]
    post = [pkt(9.0, 1, 40000, 9999)]  # before pre: cannot be the same packet
    result = match_residence(pre, post, 9999)
    assert result["matched"] == 0
    assert result["unmatched_pre"] == 1
    assert result["unmatched_post"] == 1


def test_empty_inputs():
    result = match_residence([], [], 9999)
    assert result["matched"] == 0
    assert result["residences_s"] == []
