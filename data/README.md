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

## Live collection

Two collectors run continuously (scripts/collect_traces.py):

- `vps2vps` — on alc, pinging bigguy every 200 ms
  (~/sdwan-collect/traces_vps2vps.csv on alc).
- `home_broadband` — on the team laptop, pinging alc's public IP every
  200 ms and iperf3 to bigguy every 10 min
  (data/raw/collected/home_broadband.csv).
