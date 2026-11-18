"""Sequence-level capture/app audit on existing UDP support artifacts only."""
import csv
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'testbed/outputs/ce01-matched-endpoint-support/e00-r00'

def packets(path):
    raw = path.read_bytes()
    magic = raw[:4]
    endian = '<' if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
    if magic not in (b'\xd4\xc3\xb2\xa1',b'\xa1\xb2\xc3\xd4',b'\x4d\x3c\xb2\xa1',b'\xa1\xb2\x3c\x4d'):
        raise ValueError('unsupported pcap magic')
    nano = magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
    if struct.unpack(endian+'I',raw[20:24])[0] != 1:
        raise ValueError('expected Ethernet pcap')
    pos=24; result={}
    while pos < len(raw):
        sec, frac, caplen, wirelen = struct.unpack_from(endian+'IIII',raw,pos);pos+=16
        frame=raw[pos:pos+caplen];pos+=caplen
        if len(frame)<14 or frame[12:14] != b'\x08\x00':continue
        ip=frame[14:]; ihl=(ip[0]&15)*4
        if ip[9]!=17:continue
        udp=ip[ihl:]; payload=udp[8:]
        if len(payload)<16:raise ValueError('truncated header')
        seq, sent=struct.unpack_from('!Qd',payload)
        if seq in result:raise ValueError('duplicate sequence')
        result[seq]={'sent_monotonic_s':sent,'capture_epoch_s':sec+frac/(1e9 if nano else 1e6)}
    return result


def main():
    nic=packets(RUN/'traffic.pcap')
    sender=packets(RUN/'prequeue.pcap')
    with (RUN/'receiver.csv').open() as f:
        app={int(r['seq']):float(r['received_at']) for r in csv.DictReader(f)}
    missing=sorted(set(nic)-set(app))
    first=min(v['sent_monotonic_s'] for v in sender.values())
    bins={}
    for k,v in nic.items():
        b=int(v['sent_monotonic_s']-first)
        rec=bins.setdefault(b,{'nic_packets':0,'missing_from_app':0})
        rec['nic_packets']+=1;rec['missing_from_app']+=k not in app
    runs=[]
    for k in missing:
        if not runs or k != runs[-1][-1]+1:runs.append([k,k])
        else:runs[-1][-1]=k
    out={'label':'existing_capture_sequence_audit_no_causal_claim','nic_unique':len(nic),'sender_unique':len(sender),
         'app_unique':len(app),'app_not_in_nic':len(set(app)-set(nic)), 'missing_count':len(missing),
         'missing_seq_min_max':[min(missing),max(missing)] if missing else None,
         'missing_send_offset_range_s':[min(nic[k]['sent_monotonic_s']-first for k in missing),max(nic[k]['sent_monotonic_s']-first for k in missing)] if missing else None,
         'contiguous_missing_runs':runs,'missing_by_send_second':bins,
         'mechanism':'not established by matching; no socket overflow or early-exit attribution'}
    dest=ROOT/'analysis/characterization/endpoint_support_20261118/app_gap_sequence_audit.json'
    dest.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='contiguous_missing_runs'},indent=2))
    print('contiguous_runs',len(runs),'largest',max((b-a+1 for a,b in runs),default=0))

if __name__=='__main__':main()
