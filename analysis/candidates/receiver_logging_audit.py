"""Audit existing capture IDs against receiver logs for abrupt-stop CSV truncation.

Existing artifacts only. No packet reconstruction and no global corpus verdict.
"""
import csv
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[2]

def udp_seq_ids(path):
    raw = path.read_bytes()
    magic = raw[:4]
    endian = '<' if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
    if magic not in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'):
        raise ValueError('unsupported pcap magic '+repr(magic))
    nano = magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
    if struct.unpack(endian+'I',raw[20:24])[0] != 1: raise ValueError('non-Ethernet')
    pos=24; ids=[]
    while pos < len(raw):
        sec,frac,caplen,wirelen=struct.unpack_from(endian+'IIII',raw,pos);pos+=16
        frame=raw[pos:pos+caplen];pos+=caplen
        if len(frame)<14 or frame[12:14]!=b'\x08\x00':continue
        ip=frame[14:];ihl=(ip[0]&15)*4
        if ip[9]!=17:continue
        payload=ip[ihl+8:]
        if len(payload)<16:raise ValueError('truncated UDP header')
        ids.append(struct.unpack_from('!Q',payload)[0])
    return ids


def app_ids(path):
    with path.open(newline='') as f:
        return [int(r['seq']) for r in csv.DictReader(f)]


def audit_run(run):
    receiver = run/'receiver.csv'
    sender = run/'sender.csv'
    pcap = run/'traffic.pcap'
    if not receiver.exists(): return None
    app = app_ids(receiver)
    sent = app_ids(sender) if sender.exists() else None
    item = {'run_id':run.name,'path':str(run.relative_to(ROOT)),'app_rows':len(app),
            'app_unique':len(set(app)),'sender_rows':len(sent) if sent else None,
            'app_missing_from_sender':len(set(app)-set(sent)) if sent else None}
    if pcap.exists():
        cap = udp_seq_ids(pcap)
        app_set=set(app);cap_set=set(cap);missing=sorted(cap_set-app_set)
        prefix = len(app) <= len(cap) and app == cap[:len(app)]
        dup_len = len(cap)-len(cap_set)
        item.update({'capture_packets':len(cap),'capture_unique':len(cap_set),'capture_duplicate_sequence_ids':dup_len,
                     'app_not_in_capture':len(app_set-cap_set),'missing_capture_seq_ids':len(missing),
                     'missing_min_max':[min(missing),max(missing)] if missing else None,
                     'app_is_exact_capture_prefix':prefix,
                     'confirmed_truncation_signature':len(missing)>0 and prefix and len(app_set-cap_set)==0 and sent is not None and len(app)<len(sent)})
    else:
        item['capture_audit']='suspect_unverified_no_traffic_pcap'
        # A missing capture cannot establish CSV truncation; mark only exact
        # sent->app prefix plus short app log as suspect support.
        if sent is not None:
            item['app_is_exact_sender_prefix']=app == sent[:len(app)]
    return item


def main():
    records=[]
    for corpus in ['cal_v1_full','cal_v2_perpath','ce01-smoke','ce01-matched-endpoint-support','rate-diag-p1','smoke-20261118-033510']:
        base=ROOT/'testbed/outputs'/corpus
        for run in sorted(base.glob('e*-r*')):
            x=audit_run(run)
            if x:x['corpus']=corpus;records.append(x)
    totals={'runs_audited':len(records),'confirmed_truncation_signature':sum(r.get('confirmed_truncation_signature',False) for r in records),
            'missing_capture_audits':sum('capture_audit' in r for r in records)}
    by_corpus={}
    for r in records:
        g=by_corpus.setdefault(r['corpus'],{'runs':0,'confirmed':0,'suspect_no_capture':0,'total_missing_capture_seq_ids':0})
        g['runs']+=1;g['confirmed']+=bool(r.get('confirmed_truncation_signature'));g['suspect_no_capture']+=bool('capture_audit' in r);g['total_missing_capture_seq_ids']+=r.get('missing_capture_seq_ids',0)
    result={'label':'existing_artifact_receiver_logging_audit_no_reconstruction','totals':totals,'by_corpus':by_corpus,'runs':records,
            'definition':'confirmed means app IDs are an exact prefix of unique capture IDs, no app ID outside capture, sender has more rows, and capture has fewer unique IDs than sender. Missing captures are suspect only, never confirmed.'}
    dest=ROOT/'analysis/characterization/existing_inputs_20261118/receiver_logging_audit.json';dest.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'totals':totals,'by_corpus':by_corpus},indent=2))
if __name__=='__main__':main()
