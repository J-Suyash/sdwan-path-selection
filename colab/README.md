# Colab sweep rig (Phase 5 prep)

The laptop CPU is fine for development runs. For the big hyperparameter
and seed sweeps, upload the code and datasets to a Colab GPU notebook
and run `scripts/offline_sweep.py` there.

## What to upload

Two zips prepared from the project root:

- `colab/repo.zip` — the code (`git archive` of HEAD)
- `colab/datasets.zip` — `data/datasets` (D1-D3, ~140 MB)

Refresh them before each session:

```bash
git archive -o colab/repo.zip HEAD
zip -r -q colab/datasets.zip data/datasets
```

## In Colab

1. Open `colab/offline_sweep.ipynb`, Runtime -> Change runtime type ->
   GPU (T4).
2. Run the cells in order. The upload cell takes the two zips; the
   sweep cell runs the grid from `offline_sweep.py` on the GPU.
3. The last cell downloads `offline_sweep.csv` and `models.zip`; copy
   them back into the repo (results CSV into `analysis/`, models into
   `offline/models/`).

Colab free-tier notes: sessions idle-timeout quickly, so fetch the
downloads as soon as the sweep ends. `offline_sweep.csv` appends per
run, so partial progress survives if you download it between sweeps.
