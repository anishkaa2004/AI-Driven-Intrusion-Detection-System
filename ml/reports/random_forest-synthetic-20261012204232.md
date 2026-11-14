# Results: random_forest-synthetic-20261012204232

- Dataset: synthetic-flow-v1 (generated, seed=42, n=60000) - NOT a benchmark dataset
- Split: stratified random 60/20/20 after exact-duplicate removal (train 36000, val 12000, test 12000, seed 42)
- Environment: {'python': '3.14.7', 'platform': 'macOS-27.2-arm64-arm-64bit-Mach-O', 'scikit_learn': '1.9.1', 'pandas': '3.0.6', 'numpy': '2.5.4'}

| Model | Precision (macro) | Recall (macro) | F1 (macro) | False-positive rate | Median latency (1 row) |
|---|---:|---:|---:|---:|---:|
| logistic_regression | 0.9376 | 0.9675 | 0.9519 | 0.02865 | 0.36 ms |
| decision_tree | 0.9754 | 0.9735 | 0.9745 | 0.00875 | 0.307 ms |
| random_forest (selected) | 0.9889 | 0.9751 | 0.9819 | 0.00228 | 2.847 ms |
| isolation_forest | 0.8883 | 0.7838 | 0.8137 | 0.01858 | 3.822 ms |

> These numbers come from SYNTHETIC data and do not measure real detection performance.
