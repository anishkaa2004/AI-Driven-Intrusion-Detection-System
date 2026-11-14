"""Dataset loading and cleaning into the flow-v1 raw schema.

Supported sources:
  synthetic   - generated locally (see synthetic.py); development only.
  cicids2017  - the "MachineLearningCVE" CSVs from the Canadian Institute for
                Cybersecurity (https://www.unb.ca/cic/datasets/ids-2017.html).
                Download them yourself into ml/data/CICIDS2017/ (not committed).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.features import RAW_COLUMNS  # noqa: E402

import synthetic  # noqa: E402

CICIDS_COLUMNS = {
    "Destination Port": "dst_port",
    "Flow Duration": "flow_duration",  # microseconds in the source data
    "Total Fwd Packets": "packets_out",
    "Total Backward Packets": "packets_in",
    "Total Length of Fwd Packets": "bytes_out",
    "Total Length of Bwd Packets": "bytes_in",
    "Label": "label",
}


def map_cicids_label(label: str) -> str:
    lbl = str(label).strip()
    if lbl == "BENIGN":
        return "BENIGN"
    if lbl == "PortScan":
        return "PortScan"
    if lbl == "DDoS" or lbl.startswith("DoS"):
        return "DoS"
    if lbl in ("FTP-Patator", "SSH-Patator"):
        return "BruteForce"
    if lbl.startswith("Web Attack"):
        return "WebAttack"
    if lbl == "Bot":
        return "Bot"
    return "Other"  # Infiltration, Heartbleed: too few samples to model reliably


def load_cicids2017(data_dir: Path, sample_per_file: int | None = None, seed: int = 42) -> pd.DataFrame:
    files = sorted(Path(data_dir).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No CSV files in {data_dir}. Download CICIDS2017 MachineLearningCVE CSVs.")
    parts = []
    for f in files:
        df = pd.read_csv(f, encoding="latin-1", low_memory=False)
        df.columns = [c.strip() for c in df.columns]
        missing = [c for c in CICIDS_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{f.name} is missing columns {missing}")
        df = df[list(CICIDS_COLUMNS)].rename(columns=CICIDS_COLUMNS)
        if sample_per_file and len(df) > sample_per_file:
            df = df.sample(sample_per_file, random_state=seed)
        parts.append(df)
    df = pd.concat(parts, ignore_index=True)
    df["flow_duration"] = pd.to_numeric(df["flow_duration"], errors="coerce") / 1e6
    df["label"] = df["label"].map(map_cicids_label)
    return df


def clean(df: pd.DataFrame, min_class_rows: int = 50) -> tuple[pd.DataFrame, dict]:
    """Remove invalid rows and exact duplicates; report what was removed."""
    report = {"rows_in": int(len(df))}
    df = df.copy()
    for c in RAW_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan)
    bad = df[RAW_COLUMNS].isna().any(axis=1) | (df[RAW_COLUMNS] < 0).any(axis=1)
    report["invalid_rows_removed"] = int(bad.sum())
    df = df[~bad]
    # Duplicate flows would otherwise appear in both train and test splits.
    before = len(df)
    df = df.drop_duplicates(subset=RAW_COLUMNS + ["label"])
    report["duplicate_rows_removed"] = int(before - len(df))
    # Identical features with conflicting labels are ambiguous; drop them.
    conflict = df.duplicated(subset=RAW_COLUMNS, keep=False)
    report["conflicting_label_rows_removed"] = int(conflict.sum())
    df = df[~conflict]
    counts = df["label"].value_counts()
    small = counts[counts < min_class_rows].index.tolist()
    if "Other" in counts.index:
        small = sorted(set(small) | {"Other"})
    report["dropped_classes"] = small
    df = df[~df["label"].isin(small)]
    report["rows_out"] = int(len(df))
    report["class_counts"] = {k: int(v) for k, v in df["label"].value_counts().items()}
    return df.reset_index(drop=True), report


def load_dataset(name: str, data_dir: Path | None, n: int, seed: int,
                 sample_per_file: int | None = None) -> tuple[pd.DataFrame, str]:
    if name == "synthetic":
        return synthetic.make_training_frame(n=n, seed=seed), (
            f"synthetic-flow-v1 (generated, seed={seed}, n={n}) - NOT a benchmark dataset"
        )
    if name == "cicids2017":
        d = data_dir or ROOT / "ml" / "data" / "CICIDS2017"
        return load_cicids2017(d, sample_per_file, seed), (
            f"CICIDS2017 MachineLearningCVE CSVs from {d.name}"
            + (f" (sampled {sample_per_file}/file, seed={seed})" if sample_per_file else "")
        )
    raise ValueError(f"Unknown dataset {name}")
