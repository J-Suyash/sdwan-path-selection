"""Analyze the one approved endpoint-support run, no acceptance rules."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'testbed/outputs/ce01-matched-endpoint-support'
REP = RUN / 'e00-r00'
OUT = ROOT / 'analysis/characterization/endpoint_support_20261118'
OUT.mkdir(parents=True, exist_ok=True)
window = json.loads((REP/'matched_window.json').read_text())
pre = json.loads((RUN/'privileged_preflight.json').read_text())
post = json.loads((RUN/'privileged_postflight.json').read_text())
fluid = json.loads((ROOT/'analysis/characterization/existing_inputs_20261118/ce01/run_manifest.json').read_text())
captures = {}
for name in ['traffic','prequeue','postqueue']:
    p = REP/(name+'.pcap')
    output = subprocess.check_output(['tshark','-r',str(p),'-T','fields','-e','frame.time_epoch'],text=True,stderr=subprocess.PIPE)
    times = [float(t) for t in output.splitlines() if t.strip()]
    captures[name] = {'packets':len(times),'first_epoch_s':min(times),'last_epoch_s':max(times),'span_s':max(times)-min(times)}
qdisc = (REP/'qdisc_after.txt').read_text()
counts = re.findall(r'Sent (\d+) bytes (\d+) pkt \(dropped (\d+)',qdisc)
assert len(counts) == 2
assert counts[0] == counts[1]  # propagated parent/child, do not add
wire_bytes, delivered, dropped = map(int,counts[0])
sent = window['application_summary']['sent_frames']
app_received = window['application_summary']['received_frames']
fluid_window = fluid['windows'][0]
fluid_loss = fluid_window['full_dropped_bytes']/fluid_window['full_offered_bytes']
network_loss = dropped/sent
report = {
 'label':'single_run_engineering_characterization_no_acceptance',
 'source':str(RUN.relative_to(ROOT)),
 'run_returncode':json.loads((RUN/'execution_result.json').read_text())['returncode'],
 'window':window,
 'captures_full_recording_not_matched_epoch_filtered':captures,
 'capture_logs':{p.name:p.read_text() for p in REP.glob('tcpdump*.log')},
 'qdisc':{'delivered_packets':delivered,'dropped_packets':dropped,'sent_wire_bytes':wire_bytes,
           'wire_bytes_per_delivered_packet':wire_bytes/delivered,
           'conservation':delivered+dropped==sent,
           'loss_frac_full_drained_run':network_loss},
 'nic_to_app_gap':captures['traffic']['packets']-app_received,
 'fluid':{'window':fluid_window,'loss_frac':fluid_loss},
 'descriptive_network_minus_fluid_loss_fraction':network_loss-fluid_loss,
 'descriptive_network_minus_fluid_loss_percentage_points':100*(network_loss-fluid_loss),
 'throughput_comparison_status':'application-window rate is not NIC-window rate; captures use epoch timestamps and matched endpoint uses monotonic timestamps, so no exact matched-window NIC rate is claimed without an explicit clock mapping',
 'counter_capture_conclusion':'full drained-run qdisc packet conservation and capture totals agree; full-capture delivered count is not silently substituted for matched-window app count',
 'scope':'one original-input sustained-sag engineering support run, no repetitions, uncertainty estimate, threshold tuning, boundary validation or Stage7 acceptance',
 'cleanup':{k:post[k] for k in ['s1_unchanged','run_bridges_absent','netns_veth_absent','bridges','listeners']},
 'preflight':{k:pre[k] for k in ['loadavg','cpu_count','hashes','git_head']},
 'hashes':{str(p.relative_to(RUN)):hashlib.sha256(p.read_bytes()).hexdigest() for p in RUN.rglob('*') if p.is_file()}
}
(OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['qdisc','nic_to_app_gap','descriptive_network_minus_fluid_loss_percentage_points','cleanup']},indent=2))
print('Saved',str(OUT.relative_to(ROOT)))
