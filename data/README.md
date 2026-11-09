# Data directory

Raw downloads, preprocessing intermediates and offline datasets live
here. Nothing in `raw/`, `interim/` or `processed/` is committed to git.

Sources (Section 11 of the proposal):

- LEO: WetLinks (downloaded), LENS (downloaded)
- 5G: Lumos5G (downloaded), Raca et al. (downloaded)
- Broadband: RIPE Atlas, M-Lab NDT (pending)
- Co-located broadband + 5G: team-collected (pending probe target)

## Acquisition status (2026-10-31)

- `raw/WetLinks/` — cloned from github.com/sys-uos/WetLinks (~799 MB),
  includes per-second preprocessed CSVs for Enschede and Osnabruck.
- `raw/LENS/` — cloned from github.com/clarkzjw/LENS (~23 MB).
- `raw/raca5g/` — Zenodo record 3751194, dataset zip extracted
  (~23 MB of per-second 5G throughput CSVs by app/mobility mode).
- `raw/lumos5g/` — downloaded from networking.umn.edu/lumos5g
  (Lumos5G-v1.0.zip, provided by the team). The CSV has 68,118 rows of
  per-second 5G downlink throughput (iPerf) with signal-strength context
  (RSRP/RSRQ/SINR), mobility mode and anonymized tower id.
- RIPE Atlas REST API needs an account key; M-Lab NDT needs no key.

RIPE Atlas: the account key (in .env) is read-only, so we use public
measurement results instead of creating custom measurements. First
sample: 10-minute slice of built-in ping measurement 1001 (k
root-server), 31,149 rows from ~14,000 residential probes, mean RTT
38 ms, p95 143 ms -> raw/ripe_atlas_public_1001.json. Fetch more with
`python scripts/ripe_atlas.py public-results --measurement-id 1001 ...`.

## Live collection

Two collectors run continuously (scripts/collect_traces.py):

- `vps2vps` — on bigguy (73 GB free), pinging alc's public IP every
  200 ms (~/sdwan-collect/traces_vps2vps.csv on bigguy). The earlier
  alc-hosted segment is preserved as vps2vps_alc_legacy.csv on bigguy
  and in data/raw/collected/.
- `home_broadband` — on the team laptop, pinging alc's public IP every
  200 ms and iperf3 to bigguy every 10 min
  (data/raw/collected/home_broadband.csv).

Planned: `five_g_phone` — same collector with `--interface` bound to
the phone hotspot (USB tethering preferred), longer iperf interval to
limit metered data use.

## Processed (Section 11.2)

Run `python scripts/preprocess_traces.py all` to rebuild. Output in
`data/processed/<source>.parquet` with a uniform 1-second schema:
utc, source, site, rtt_ms, jitter_ms, loss_frac, dl_mbps, ul_mbps,
outage, meta.

## Offline datasets (Section 8.3)

The transition schema is versioned by `scripts/generate_datasets.py` and
includes `obs`, `action`, `reward`, `next_obs`, per-class constraint flags,
`behavior_action_prob`, workload profile/regime, random seed, trace segment,
policy version and simulator version. Episode boundaries are defined by policy
and episode metadata, not by a global maximum time value.

The checked-in D1-D3 files are legacy outputs from the pre-audit emulator and
must not be used for WIS or final claims. Regenerate after the workload,
queue and cross-engine validation gates in `docs/issue_register.md` pass.
