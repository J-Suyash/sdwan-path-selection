"""Offline file-buffer audit using existing capture packet sequence/size only."""
import csv
import io
import json
from pathlib import Path
import sys

from analysis.candidates.endpoint_app_gap_sequence_audit import packets

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT/'testbed/outputs/ce01-matched-endpoint-support/e00-r00'
p = Path('/tmp/endpoint_receiver_buffer_offline.csv')
nic=packets(RUN/'traffic.pcap')
with (RUN/'receiver.csv').open() as f:
    app = list(csv.DictReader(f))
h = p.open('w',newline='')
w=csv.writer(h)
w.writerow(('seq','sent_at','received_at'))
for seq,item in nic.items():
    # Epoch timestamps cannot be treated as monotonic. For this buffer
    # length reproduction only, choose same-width positive monotonic
    # values, never use these to estimate packet delay.
    sent=item['sent_monotonic_s']
    w.writerow((seq,f'{sent:.9f}',f'{sent+1.0:.9f}'))
visible_before_flush = p.read_bytes()
rows_before = list(csv.DictReader(io.StringIO(visible_before_flush.decode())))
h.flush()
visible_after_flush = p.read_bytes()
rows_after = list(csv.DictReader(io.StringIO(visible_after_flush.decode())))
h.close()
observed_seqs = [int(r['seq']) for r in app]
prefix_seqs = [int(r['seq']) for r in rows_before]
result={'label':'offline_buffer_reproduction_not_new_network_run',
        'python':sys.version,'io_DEFAULT_BUFFER_SIZE':io.DEFAULT_BUFFER_SIZE,
        'observed_receiver_rows':len(app),'nic_packets_written_offline':len(nic),
        'visible_rows_before_explicit_flush':len(rows_before),
        'visible_rows_after_explicit_flush':len(rows_after),
        'observed_sequence_list_equals_unflushed_visible_prefix':observed_seqs==prefix_seqs,
        'unflushed_bytes':len(visible_after_flush)-len(visible_before_flush),
        'scope':'synthetic timestamps preserve field widths only; no inferred packet delay or receiver receipt time',
        'interpretation':'an abrupt receiver termination can lose its unwritten CSV buffer; matching prefix is direct evidence for a logging artifact, not evidence of socket packet loss'}
out=ROOT/'analysis/characterization/endpoint_support_20261118/buffer_reproduction.json'
out.write_text(json.dumps(result,indent=2)+'\n')
p.unlink()
print(json.dumps(result,indent=2))
