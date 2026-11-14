"""Versioned ML inference.

Only a model listed in `<artifacts_dir>/manifest.json` is loaded, only from
inside the artifacts directory, and only if its SHA-256 matches the manifest.
Serialized scikit-learn models are pickles, which can execute code when
loaded, so artifacts must come from this project's own training script.
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ModelRegistry
from app.services.features import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    compute_features,
    has_required_counters,
)

log = logging.getLogger("aiids.ml")

SCORE_MEANING = "Model class score (predict_proba); not calibrated to real-world risk"


@dataclass
class Prediction:
    label: str
    score: float


class ModelService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.pipeline = None
        self.manifest: dict | None = None
        self.load_error: str | None = None
        self.last_latency_ms: float | None = None

    @property
    def loaded(self) -> bool:
        return self.pipeline is not None

    @property
    def version(self) -> str | None:
        return self.manifest["model_version"] if self.manifest else None

    @property
    def benign_label(self) -> str:
        return (self.manifest or {}).get("benign_label", "BENIGN")

    def load(self, artifacts_dir: str | None = None) -> bool:
        base = Path(artifacts_dir or get_settings().model_artifacts_dir).resolve()
        manifest_path = base / "manifest.json"
        with self._lock:
            self.pipeline, self.manifest, self.load_error = None, None, None
            try:
                if not manifest_path.is_file():
                    raise FileNotFoundError(
                        f"No model manifest at {manifest_path}. Run `python ml/src/train.py` first."
                    )
                full = json.loads(manifest_path.read_text())
                m = full["active_model"]
                artifact = (base / m["artifact"]).resolve()
                if artifact.parent != base or not artifact.is_file():
                    raise ValueError("Model artifact must be a file directly inside the artifacts dir")
                digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                if digest != m["sha256"]:
                    raise ValueError("Model artifact checksum does not match manifest; refusing to load")
                if m["feature_schema_version"] != FEATURE_SCHEMA_VERSION or m["feature_columns"] != FEATURE_COLUMNS:
                    raise ValueError("Model feature schema is incompatible with this backend")
                self.pipeline = joblib.load(artifact)
                self.manifest = {**m, "experiments": full.get("experiments", []),
                                 "environment": full.get("environment", {})}
                log.info("Loaded model %s", m["model_version"])
                return True
            except Exception as exc:  # report, keep running rule-only
                self.load_error = str(exc)
                log.warning("ML model not loaded: %s", exc)
                return False

    def predict(self, records: list[dict]) -> list[Prediction | None]:
        """Predict for records that have the required counters; None otherwise."""
        results: list[Prediction | None] = [None] * len(records)
        if not self.loaded:
            return results
        idx = [i for i, r in enumerate(records) if has_required_counters(r)]
        if not idx:
            return results
        raw = pd.DataFrame([records[i] for i in idx])
        X = compute_features(raw)
        t0 = time.perf_counter()
        with self._lock:
            proba = self.pipeline.predict_proba(X)
            classes = list(self.pipeline.classes_)
        self.last_latency_ms = (time.perf_counter() - t0) * 1000
        for row, i in enumerate(idx):
            j = int(proba[row].argmax())
            results[i] = Prediction(label=str(classes[j]), score=float(proba[row][j]))
        return results

    def sync_registry(self, db: Session) -> None:
        if not self.manifest:
            return
        m = self.manifest
        row = db.scalar(select(ModelRegistry).where(ModelRegistry.model_version == m["model_version"]))
        db.execute(update(ModelRegistry).values(is_active=False))
        metrics = {
            "test": m.get("metrics", {}),
            "experiments": m.get("experiments", []),
            "labels": m.get("labels", []),
            "feature_columns": m.get("feature_columns", []),
            "environment": m.get("environment", {}),
            "split": m.get("split", {}),
        }
        trained_at = datetime.fromisoformat(m["trained_at"].rstrip("Z")) if m.get("trained_at") else None
        if row is None:
            row = ModelRegistry(
                model_name=m["model_name"], model_version=m["model_version"],
                artifact_reference=m["artifact"], artifact_sha256=m["sha256"],
                feature_schema_version=m["feature_schema_version"],
                dataset_reference=m.get("dataset_reference", "unknown"),
                trained_at=trained_at, metrics_json=metrics,
            )
            db.add(row)
        row.is_active = True
        row.metrics_json = metrics
        db.commit()


model_service = ModelService()
