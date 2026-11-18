"""Real subprocess SIGTERM regression, fake socket only. No network traffic."""
import csv
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

CHILD = r'''
import pathlib,struct,sys,time
from types import SimpleNamespace
from testbed import traffic
out=pathlib.Path(sys.argv[1]);ready=pathlib.Path(sys.argv[2]); mode=sys.argv[3]
class FakeSocket:
    def __init__(self):self.i=0
    def setsockopt(self,*a):pass
    def bind(self,*a):pass
    def settimeout(self,*a):pass
    def recvfrom(self,*a):
        if self.i==55900:
            ready.write_text('ready')
            time.sleep(30)
            raise RuntimeError('offline timeout')
        i=self.i;self.i+=1
        return struct.pack('!Qd',i,220000.0+i/10000),None
traffic.socket.socket=lambda *a:FakeSocket()
traffic.time=SimpleNamespace(monotonic=lambda:220000.0)
if mode=='fixed':
    sys.argv=['traffic','receiver','udp','--port','1','--timeout','600','--idle-timeout','600','--out',str(out)]
    traffic.main()
else:
    # Control path: same receiver function without main's SIGTERM handler.
    traffic.run_udp_receiver(SimpleNamespace(bind='127.0.0.1',port=1,idle_timeout=600,timeout=600,out=out))
'''


@pytest.mark.parametrize('mode', ['control', 'fixed'])
def test_receiver_sigterm_preserves_written_records_with_graceful_handler(tmp_path, mode):
    output, ready = tmp_path/'receiver.csv', tmp_path/'ready'
    env=dict(os.environ,PYTHONPATH=str(Path.cwd()))
    p=subprocess.Popen([sys.executable,'-c',CHILD,str(output),str(ready),mode],env=env,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        deadline=time.monotonic()+15
        while not ready.exists():
            if p.poll() is not None:
                _,stderr=p.communicate()
                pytest.fail(stderr.decode())
            if time.monotonic()>deadline:pytest.fail('fake receiver failed to finish writes')
            time.sleep(0.01)
        p.send_signal(signal.SIGTERM)
        _,stderr=p.communicate(timeout=5)
        assert not stderr
        with output.open() as f:rows=list(csv.DictReader(f))
        if mode=='fixed':
            assert p.returncode==0
            assert len(rows)==55900
            assert [int(r['seq']) for r in rows]==list(range(55900))
        else:
            assert p.returncode==-signal.SIGTERM
            # Buffer size varies by Python version. A nonempty buffered
            # tail is lost, never prescribe one interpreter's row count.
            assert 0 < len(rows) < 55900
    finally:
        if p.poll() is None:p.kill();p.wait()
