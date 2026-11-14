"""Evaluation metrics for multiclass flow classifiers.

False-positive rate is defined in a binary benign-vs-attack setting:
    FPR = (# benign flows predicted as any attack class) / (# benign flows)
Detection rate is the matching binary recall:
    DR  = (# attack flows predicted as any attack class) / (# attack flows)
Per-class precision/recall/F1 are one-vs-rest; "macro" is their unweighted mean.
"""

import time

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def classification_metrics(y_true, y_pred, labels: list[str], benign: str = "BENIGN",
                           attack_score=None) -> dict:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=labels,
                                                    average="macro", zero_division=0)
    is_benign = y_true == benign
    pred_attack = y_pred != benign
    out = {
        "labels": labels,
        "per_class": {
            lbl: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
                  "f1": round(float(f[i]), 4), "support": int(s[i])}
            for i, lbl in enumerate(labels)
        },
        "macro": {"precision": round(float(mp), 4), "recall": round(float(mr), 4), "f1": round(float(mf), 4)},
        "accuracy": round(float((y_true == y_pred).mean()), 4),
        "false_positive_rate": round(float(pred_attack[is_benign].mean()), 5) if is_benign.any() else None,
        "detection_rate": round(float(pred_attack[~is_benign].mean()), 5) if (~is_benign).any() else None,
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "test_rows": int(len(y_true)),
    }
    if attack_score is not None and is_benign.any() and (~is_benign).any():
        out["binary_pr_auc"] = round(float(average_precision_score(~is_benign, attack_score)), 4)
    return out


def latency(model, X, repeats: int = 200) -> dict:
    """Median/p95 single-row latency and batch throughput on this machine."""
    rows = X.iloc[: min(repeats, len(X))]
    singles = []
    for i in range(len(rows)):
        t0 = time.perf_counter()
        model.predict(rows.iloc[[i]])
        singles.append((time.perf_counter() - t0) * 1000)
    batch = X.iloc[: min(5000, len(X))]
    t0 = time.perf_counter()
    model.predict(batch)
    elapsed = time.perf_counter() - t0
    return {
        "single_row_ms_median": round(float(np.median(singles)), 3),
        "single_row_ms_p95": round(float(np.percentile(singles, 95)), 3),
        "batch_rows": int(len(batch)),
        "batch_rows_per_second": round(len(batch) / elapsed, 1) if elapsed > 0 else None,
    }
