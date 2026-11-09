# Matched Emulator / Mininet Settings

Recorded 2026-11-10 as the base for cross-engine validation
(owner decision 8). The Mininet scenario and the emulator must share the
same nominal link populations, delay semantics and queue accounting so
that differences reflect engine behaviour, not configuration drift.

## Verified trace medians (source of matched values)

| underlay | trace | RTT median (ms) | one-way = RTT/2 (ms) | jitter RTT med (ms) | loss med | DL median (Mbps) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| bb | collected vps2vps/home | 187.4 | 93.7 | 0.6 | 0.000 | n/a |
| five_g | Raca5G ping | 75.0 | 37.5 | 2.0 | 0.000 | p95 56.3 |
| leo | WetLinks ping | 61.9 | 31.0 | 0.0 | 0.000 | 221.0 |

Lumos5G carries no RTT; if it becomes the 5G leg source, delay values
must come from a separate measurement, not from throughput.

## Matched scenario v1 (`testbed/scenarios/switch_calibration_v1.json`)

| setting | Mininet value | emulator value | status |
| --- | --- | --- | --- |
| bb delay | 93.7 ms one-way | trace median / 2 | verified median |
| five_g delay | 37.5 ms one-way | trace median / 2 | verified median |
| leo delay | 31.0 ms one-way | trace median / 2 | verified median |
| bb capacity | 200 Mbps | `cap_mbps.bb` 200 | matched |
| five_g capacity | 150 Mbps | emulator cap 300 (trace p95 56) | **mismatch risk**: emulator service cap must be set to 150 for matched runs |
| leo capacity | 100 Mbps | emulator cap 200 (trace median 221) | **mismatch risk**: set 100 for matched runs |
| capacity metric | tbf rate | fluid queue service | engine approximation; calibrate |
| queue buffer | per-path packets (bb 4166, 5g 3125, leo 2083) = capacity×0.25 s / 1500 B | `queue_buffer_s` 0.25 | matched |
| queue discipline | single FIFO netem/tbf queue per path | `fifo-fluid` per underlay | engine abstraction; label |
| transport | kernel TCP / paced UDP fixed-size payload | `fluid-rate-v1` | engine abstraction; label |
| SLA thresholds | same one-way thresholds | same | matched |
| switch mechanism | OVS flow-rule `mod-flows` on 4 selectors | instantaneous assignment + calibrated interruption | engine abstraction; label |

## Current round (2026-11-10 calibration sweep)

The running 120-run calibration sweep was launched with the shared
`queue_limit_packets = 1000` budget because per-path limits landed after
the run started. Per-run in-flight and occupancy fractions are recorded
per row, so the calibration rows remain usable covariates. The next
calibration round (owner decision 8, after thresholds) runs with the
per-path queue limits so buffer bytes match the emulator exactly.

## Validation thresholds policy

Thresholds for cross-engine agreement are **not** set here. They are
derived after the repeated measurement audit: per-key repeatability CVs
from `scripts/build_switch_calibration.py` plus natural variation
analysis set the tolerance the emulator must respect. The plan's
NRMSE/Wasserstein cutoff values remain unapproved (issue register).
