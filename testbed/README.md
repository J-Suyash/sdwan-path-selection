# Testbed package

Mininet + Open vSwitch + os-ken/Ryu topology for matched branch/hub
experiments. Use `tc-netem` for delay, jitter and loss and a rate limiter
such as TBF for capacity. The packet-level testbed is the calibration source
for kernel TCP/QUIC behavior; it is not replaced by the Gymnasium fluid model.

Each controlled switching run records the old/new path RTT and jitter,
packets in flight, flow type, transport, rule-installation method/time,
queue occupancy, interruption duration, loss, reordering, retransmissions
and application QoS. Populate `data/switching_calibration_template.csv` only
from repeated measured runs, then point `SDWanConfig.switching_calibration_path`
to the resulting file.

## Execution environment

Mininet 2.3 is installed for the system Python, not inside the project
virtual environment. Dry-runs and analysis use `.venv/bin/python`; real
topology execution uses `/usr/bin/python3` or `/usr/bin/python3.14`:

```bash
.venv/bin/python -m testbed.run_switch_calibration \
  --scenario testbed/scenarios/smoke.json --dry-run

sudo env PYTHONPATH="$PWD" /usr/bin/python3 -m \
  testbed.run_switch_calibration --scenario testbed/scenarios/smoke.json
```

The runner creates one directory per repetition, records sender/receiver
logs, a PCAP, qdisc snapshots and `metrics.json`, then writes
`switch_metrics_raw.csv`. The raw file is marked `raw_unvalidated`; it is not
automatically enabled as emulator calibration.

The selected scenario uses controlled `tc-netem`/TBF factors. These are
experimental inputs, not claims about the population distribution. The
provisional `medium` branch profile and normal regime apply to the matched
workload definition.
