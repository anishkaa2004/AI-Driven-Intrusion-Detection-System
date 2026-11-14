"""Train, compare and export flow classifiers.

    python ml/src/train.py                         # synthetic data (development)
    python ml/src/train.py --dataset cicids2017    # real benchmark (download first)

Workflow (blueprint section 13.2): load -> clean/dedupe -> stratified
train/validation/test split -> fit preprocessing on train only -> train
baselines -> select on validation macro-F1 -> evaluate every model once on
the held-out test set -> save the selected pipeline with a manifest.
"""

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler
from sklearn.tree import DecisionTreeClassifier

import prepare_data
from evaluate import classification_metrics, latency

from app.services.features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, compute_features

ROOT = prepare_data.ROOT
BENIGN = "BENIGN"


def build_models(seed: int) -> dict[str, Pipeline]:
    imp = lambda: SimpleImputer(strategy="median")  # noqa: E731
    return {
        "logistic_regression": Pipeline([
            ("impute", imp()), ("log", _log1p()), ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)),
        ]),
        "decision_tree": Pipeline([
            ("impute", imp()),
            ("clf", DecisionTreeClassifier(max_depth=12, min_samples_leaf=5,
                                           class_weight="balanced", random_state=seed)),
        ]),
        "random_forest": Pipeline([
            ("impute", imp()),
            ("clf", RandomForestClassifier(n_estimators=150, min_samples_leaf=2, n_jobs=-1,
                                           class_weight="balanced_subsample", random_state=seed)),
        ]),
    }


def _log1p() -> FunctionTransformer:
    # Counters are validated as non-negative; log1p tames their heavy tails for
    # linear/anomaly models. np.log1p pickles by reference, so the backend can
    # load the pipeline without importing this script.
    return FunctionTransformer(np.log1p, feature_names_out="one-to-one")


def feature_importance(name: str, pipe: Pipeline) -> dict[str, float]:
    clf = pipe.named_steps["clf"]
    if hasattr(clf, "feature_importances_"):
        vals = clf.feature_importances_
    elif hasattr(clf, "coef_"):
        vals = np.abs(clf.coef_).mean(axis=0)
        vals = vals / vals.sum()
    else:
        return {}
    pairs = sorted(zip(FEATURE_COLUMNS, vals), key=lambda p: -p[1])
    return {k: round(float(v), 4) for k, v in pairs}


def isolation_forest_experiment(X_train, y_train, X_test, y_test, seed: int) -> dict:
    """Unsupervised anomaly experiment: fit on benign training flows only.

    Its anomaly score is not an attack probability; it is reported in a
    binary benign/attack setting for comparison only and never deployed.
    """
    pipe = Pipeline([("impute", SimpleImputer(strategy="median")), ("log", _log1p()),
                     ("clf", IsolationForest(n_estimators=200, contamination=0.02, random_state=seed))])
    pipe.fit(X_train[y_train == BENIGN])
    anomalous = pipe.predict(X_test) == -1
    y_pred = np.where(anomalous, "ATTACK", BENIGN)
    y_bin = np.where(np.asarray(y_test) == BENIGN, BENIGN, "ATTACK")
    m = classification_metrics(y_bin, y_pred, [BENIGN, "ATTACK"], attack_score=-pipe.decision_function(X_test))
    m["note"] = "Binary benign-vs-attack; fitted on benign training rows only; contamination=0.02"
    m["latency"] = latency(pipe, X_test)
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", choices=["synthetic", "cicids2017"], default="synthetic")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--rows", type=int, default=60_000, help="synthetic rows to generate")
    ap.add_argument("--sample-per-file", type=int, default=None, help="cicids2017: rows sampled per CSV")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=ROOT / "ml" / "artifacts")
    ap.add_argument("--no-isolation-forest", action="store_true")
    args = ap.parse_args()

    np.random.seed(args.seed)
    raw, dataset_ref = prepare_data.load_dataset(args.dataset, args.data_dir, args.rows, args.seed,
                                                 args.sample_per_file)
    df, clean_report = prepare_data.clean(raw)
    print(f"Dataset: {dataset_ref}\nClean report: {json.dumps(clean_report, indent=2)}")

    X = compute_features(df)
    y = df["label"].to_numpy()
    labels = [BENIGN] + sorted(set(y) - {BENIGN})

    # 60/20/20 stratified split. Exact duplicates were removed beforehand to
    # reduce leakage between splits. The test set is used once, at the end.
    X_tmp, X_test, y_tmp, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=args.seed)
    X_train, X_val, y_train, y_val = train_test_split(X_tmp, y_tmp, test_size=0.25, stratify=y_tmp,
                                                      random_state=args.seed)
    split = {"method": "stratified random 60/20/20 after exact-duplicate removal",
             "train": len(y_train), "validation": len(y_val), "test": len(y_test), "seed": args.seed}
    print(f"Split: {split}")

    experiments = []
    fitted = {}
    for name, pipe in build_models(args.seed).items():
        print(f"Training {name} ...")
        pipe.fit(X_train, y_train)
        if hasattr(pipe.named_steps["clf"], "n_jobs"):
            # Single-threaded inference: the backend scores small batches.
            pipe.named_steps["clf"].n_jobs = 1
        val = classification_metrics(y_val, pipe.predict(X_val), labels)
        fitted[name] = pipe
        experiments.append({"model_name": name, "validation": val})
    best = max(experiments, key=lambda e: e["validation"]["macro"]["f1"])
    print(f"Selected on validation macro-F1: {best['model_name']}")

    # Final, single evaluation of every model on the held-out test set.
    for exp in experiments:
        pipe = fitted[exp["model_name"]]
        proba = pipe.predict_proba(X_test)
        benign_idx = list(pipe.classes_).index(BENIGN)
        exp["test"] = classification_metrics(y_test, pipe.predict(X_test), labels,
                                             attack_score=1 - proba[:, benign_idx])
        exp["test"]["latency"] = latency(pipe, X_test)
        exp["feature_importance"] = feature_importance(exp["model_name"], pipe)
        exp["selected"] = exp is best
    if not args.no_isolation_forest:
        print("Running Isolation Forest anomaly experiment ...")
        experiments.append({"model_name": "isolation_forest", "selected": False, "deployable": False,
                            "test": isolation_forest_experiment(X_train, y_train, X_test, y_test, args.seed)})

    now = datetime.now(timezone.utc)
    version = f"{best['model_name']}-{args.dataset}-{now:%Y%m%d%H%M%S}"
    args.out.mkdir(parents=True, exist_ok=True)
    artifact = args.out / f"{version}.joblib"
    joblib.dump(fitted[best["model_name"]], artifact)
    sha = hashlib.sha256(artifact.read_bytes()).hexdigest()

    environment = {"python": sys.version.split()[0], "platform": platform.platform(),
                   "scikit_learn": sklearn.__version__, "pandas": pd.__version__, "numpy": np.__version__}
    manifest = {
        "active_model": {
            "model_name": best["model_name"], "model_version": version, "artifact": artifact.name,
            "sha256": sha, "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_columns": FEATURE_COLUMNS, "labels": labels, "benign_label": BENIGN,
            "dataset": args.dataset, "dataset_reference": dataset_ref,
            "trained_at": now.isoformat().replace("+00:00", "Z"), "split": split,
            "clean_report": clean_report, "metrics": best["test"],
        },
        "experiments": experiments,
        "environment": environment,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    reports = ROOT / "ml" / "reports"
    reports.mkdir(exist_ok=True)
    (reports / f"{version}.json").write_text(json.dumps(manifest, indent=2))
    (reports / f"{version}.md").write_text(results_markdown(manifest))
    print(f"\nSaved {artifact.relative_to(ROOT)} and manifest.json\n")
    print(results_markdown(manifest))


def results_markdown(m: dict) -> str:
    a = m["active_model"]
    lines = [
        f"# Results: {a['model_version']}", "",
        f"- Dataset: {a['dataset_reference']}",
        f"- Split: {a['split']['method']} (train {a['split']['train']}, val {a['split']['validation']}, "
        f"test {a['split']['test']}, seed {a['split']['seed']})",
        f"- Environment: {m['environment']}", "",
        "| Model | Precision (macro) | Recall (macro) | F1 (macro) | False-positive rate | Median latency (1 row) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for e in m["experiments"]:
        t = e["test"]
        name = e["model_name"] + (" (selected)" if e.get("selected") else "")
        lines.append(f"| {name} | {t['macro']['precision']} | {t['macro']['recall']} | {t['macro']['f1']} | "
                     f"{t['false_positive_rate']} | {t['latency']['single_row_ms_median']} ms |")
    if a["dataset"] == "synthetic":
        lines += ["", "> These numbers come from SYNTHETIC data and do not measure real detection performance."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
