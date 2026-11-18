import pytest

from testbed.clock_map import classify_frame, frame_epochs_from_pcap, map_boundary, mapped_capture_counts


def sample(t, epoch=None, bracket=0.0):
    if epoch is None: epoch = 1000 + t
    return {"label":str(t), "epoch_before_s":epoch, "monotonic_s":t, "epoch_after_s":epoch+bracket, "sampling_bracket_s":bracket, "sample_order_offset_s":0}


def test_classify_boundaries():
    assert classify_frame(9.9,10,20)=="before"
    assert classify_frame(10,10,20)=="inside"
    assert classify_frame(20.1,10,20)=="after"
    with pytest.raises(ValueError):classify_frame(1,2,1)


def test_sparse_boundary_envelope_and_strict_counts():
    samples=[sample(0,bracket=0.0005),sample(1,bracket=0.0005),sample(2,bracket=0.0005),sample(3,bracket=0.0005)]
    lo,hi=map_boundary(samples,1.5)
    assert 1000.999 <= lo <= hi <= 1002.0015
    r=mapped_capture_counts([1000.5,1001.4994,1001.5,1002.5006,1002.6],samples,1.5,2.5,boundary_safety_s=0.0001)
    assert r["strict_lower_bound_count"]==0
    assert r["sampled_envelope_upper_bound_count"]==4
    assert r["boundary_uncertain_count"]==4
    assert "no acceptance interval" in r["label"]


def test_wall_step_makes_timing_unavailable():
    samples=[sample(0),sample(1),sample(2,epoch=1012),sample(3,epoch=1013)]
    with pytest.raises(ValueError,match="step|nonlinearity"):
        mapped_capture_counts([],samples,0.5,2.5,boundary_safety_s=0.0001)


def test_boundary_outside_sampled_range_fails_closed():
    with pytest.raises(ValueError,match="outside sampled"):
        mapped_capture_counts([],[sample(1),sample(2)],0,1.5,boundary_safety_s=0.0001)


def test_capture_timestamp_order_is_not_reordering_logic(tmp_path):
    # Capture-frame clock order is handled as timestamp data. Packet
    # reordering is a separate sequence-order observation.
    p=tmp_path/'x.pcap';p.write_bytes(b'\xd4\xc3\xb2\xa1'+(2<<16).to_bytes(4,'little')+b'\0'*12+(1).to_bytes(4,'little')+
        (1).to_bytes(4,'little')+(0).to_bytes(4,'little')+(1).to_bytes(4,'little')+(1).to_bytes(4,'little')+b'x'+
        (0).to_bytes(4,'little')+(500000).to_bytes(4,'little')+(1).to_bytes(4,'little')+(1).to_bytes(4,'little')+b'x')
    assert frame_epochs_from_pcap(p)==[1.0,0.5]


def test_uncertainty_wider_than_window_yields_zero_strict_bound():
    samples=[sample(0),sample(1),sample(2),sample(3)]
    r=mapped_capture_counts([1001.5,1002.5],samples,1.5,2.5,boundary_safety_s=0.001)
    assert r["strict_lower_bound_count"]==0
    assert r["sampled_envelope_upper_bound_count"]==2
