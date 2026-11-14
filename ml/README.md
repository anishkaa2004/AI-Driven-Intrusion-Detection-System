# ML pipeline

```bash
.venv/bin/python ml/src/train.py                       # synthetic data, ~20 s
.venv/bin/python ml/src/train.py --dataset cicids2017  # real benchmark
```

Outputs:
- `ml/artifacts/<version>.joblib` — selected scikit-learn pipeline
- `ml/artifacts/manifest.json` — version, SHA-256, feature columns, labels, dataset reference, split, metrics of every model
- `ml/reports/<version>.{json,md}` — full metrics and a results table for the report

Restart the backend after training; it loads the model named in `manifest.json` (and only that one,
only if the checksum matches).

## Using CICIDS2017

1. Download the **MachineLearningCVE** CSVs from the Canadian Institute for Cybersecurity:
   https://www.unb.ca/cic/datasets/ids-2017.html (check the licence/terms; cite the dataset).
2. Put the CSV files in `ml/data/CICIDS2017/` (git-ignored).
3. Train, optionally sampling to keep it fast:
   ```bash
   .venv/bin/python ml/src/train.py --dataset cicids2017 --sample-per-file 100000
   ```

Column mapping (`prepare_data.py`): `Flow Duration` (µs → s), `Total Fwd Packets` → packets_out,
`Total Backward Packets` → packets_in, `Total Length of Fwd/Bwd Packets` → bytes_out/in,
`Destination Port` → dst_port. Labels are grouped into `BENIGN, DoS (incl. DDoS), PortScan,
BruteForce (FTP/SSH-Patator), WebAttack, Bot`; Infiltration and Heartbleed are dropped (too few rows).

## Methodology (blueprint §13)

- Invalid rows, exact duplicates and identical-feature/conflicting-label rows are removed **before**
  splitting (reduces train/test leakage); counts are recorded in `clean_report`.
- Stratified 60/20/20 train/validation/test, seed 42. Preprocessing (imputer, log, scaler) lives inside
  each pipeline, so it is fit on training data only.
- Class imbalance: `class_weight="balanced"` (training only).
- Models: Logistic Regression (baseline), Decision Tree (explainable), Random Forest; Isolation Forest
  as an unsupervised binary experiment (fitted on benign training rows; never deployed).
- Selection on validation macro-F1; every model is then evaluated **once** on the test split.
- FPR = benign flows predicted as any attack / benign flows. Per-class metrics are one-vs-rest; macro = unweighted mean.
- A random split of CICIDS flows is optimistic (flows from the same attack session land on both sides).
  For a stricter evaluation, train on some capture days and test on others, and say which you used.

## Current artifact

The bundled model was trained on **synthetic** data (`synthetic.py`). Its near-perfect metrics show
that the pipeline works end to end; they are not evidence of real detection performance.
