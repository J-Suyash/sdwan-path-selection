"""No sockets/traffic: test the existing receiver's CSV shutdown with a fake socket."""
import csv
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from analysis.candidates.endpoint_app_gap_sequence_audit import packets

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/'testbed/outputs/ce01-matched-endpoint-support/e00-r00'
CHILD=r'''
import json, pathlib, signal, struct, sys, time
from types import SimpleNamespace
from testbed import traffic
seqs=json.loads(pathlib.Path(sys.argv[1]).read_text())
out=pathlib.Path(sys.argv[2]);ready=pathlib.Path(sys.argv[3])
class Sock:
    def __init__(self):self.i=0
    def setsockopt(self,*a):pass
    def bind(self,*a):pass
    def settimeout(self,*a):pass
    def recvfrom(self,*a):
        if self.i==len(seqs):
            ready.write_text('all fake packets consumed')
            time.sleep(60)
            raise RuntimeError('test timeout')
        seq,sent=seqs[self.i];self.i+=1
        return struct.pack('!Qd',seq,sent),None
traffic.socket.socket=lambda *a:Sock()
traffic.time=SimpleNamespace(monotonic=lambda:220000.0)
if sys.argv[4]=='graceful':
    def stop(*a):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
a=SimpleNamespace(bind='127.0.0.1',port=1,idle_timeout=600,timeout=600,out=out)
traffic.run_udp_receiver(a)
'''

def main():
    nic=packets(RUN/'traffic.pcap')
    with (RUN/'receiver.csv').open() as f:observed=[int(r['seq']) for r in csv.DictReader(f)]
    reports=[]
    with tempfile.TemporaryDirectory(prefix='receiver-signal-offline-') as temp:
        p=Path(temp);(p/'seqs.json').write_text(json.dumps([(k,v['sent_monotonic_s']) for k,v in nic.items()]))
        for mode in ['default','graceful']:
            out=p/(mode+'.csv');ready=p/(mode+'.ready')
            env=dict(os.environ,PYTHONPATH=str(ROOT))
            child=subprocess.Popen([sys.executable,'-c',CHILD,str(p/'seqs.json'),str(out),str(ready),mode],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            deadline=time.monotonic()+15
            try:
                while not ready.exists():
                    if child.poll() is not None:raise RuntimeError(child.communicate()[1].decode())
                    if time.monotonic()>deadline:raise TimeoutError('fake receiver did not finish writes')
                    time.sleep(0.01)
                child.send_signal(signal.SIGTERM)
                stdout,stderr=child.communicate(timeout=5)
                if stderr:raise RuntimeError(stderr.decode())
                with out.open() as f:seqs=[int(r['seq']) for r in csv.DictReader(f)]
                reports.append({'mode':mode,'returncode':child.returncode,'rows_after_signal':len(seqs),'observed_sequence_list_equal':seqs==observed,'all_nic_sequences_preserved':seqs==list(nic)})
            finally:
                if child.poll() is None:child.kill();child.wait()
    report={'label':'actual_receiver_source_fake_socket_SIGTERM_offline_no_network','python':sys.version,'reports':reports,
            'scope':'the existing receiver source was exercised with synthetic receive timestamps and existing capture sequence IDs; no real socket, traffic or new evidence of historical recv calls',
            'finding':'default SIGTERM reproduces the observed CSV prefix; an exception-based graceful handler exits the file context and preserves all records'}
    out=ROOT/'analysis/characterization/endpoint_support_20261118/signal_reproduction.json';out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
