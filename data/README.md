# Data directory

Raw downloads, preprocessing intermediates and offline datasets live
here. Nothing in `raw/`, `interim/` or `processed/` is committed to git.

Sources (Section 11 of the proposal):

- LEO: WetLinks (downloaded), LENS (downloaded)
- 5G: Raca et al. (downloaded), Lumos5G (pending IEEE DataPort account)
- Broadband: RIPE Atlas, M-Lab NDT (pending)
- Co-located broadband + 5G: team-collected (pending probe target)

## Acquisition status (2026-10-31)

- `raw/WetLinks/` — cloned from github.com/sys-uos/WetLinks (~799 MB),
  includes per-second preprocessed CSVs for Enschede and Osnabruck.
- `raw/LENS/` — cloned from github.com/clarkzjw/LENS (~23 MB).
- `raw/raca5g/` — Zenodo record 3751194, dataset zip extracted
  (~23 MB of per-second 5G throughput CSVs by app/mobility mode).
- Lumos5G dataset lives on IEEE DataPort (free account required):
  https://ieee-dataport.org/open-access/lumos5g-dataset
- RIPE Atlas REST API needs an account key; M-Lab NDT needs no key.
