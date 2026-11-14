"""Canonical feature extraction for schema flow-v1.

This module is the single source of truth for model features: the training
code in ml/src imports it, and the inference service uses it at runtime, so
training and inference apply exactly the same transformation.

Only per-flow counters are used. Identifiers (IP addresses, event ids) and
timestamps are deliberately excluded to avoid learning dataset artifacts.
"""

import numpy as np
import pandas as pd

FEATURE_SCHEMA_VERSION = "flow-v1"

RAW_COLUMNS = [
    "flow_duration",  # seconds
    "packets_in",
    "packets_out",
    "bytes_in",
    "bytes_out",
    "dst_port",
]

FEATURE_COLUMNS = [
    "flow_duration",
    "packets_in",
    "packets_out",
    "bytes_in",
    "bytes_out",
    "dst_port",
    "dst_port_well_known",
    "bytes_per_packet_in",
    "bytes_per_packet_out",
    "packets_per_second",
    "bytes_per_second",
    "out_in_packet_ratio",
]


def has_required_counters(record: dict) -> bool:
    """ML is only applied when the counters were actually observed.

    Missing counters are never imputed as zeros for live inference, because
    that would be inferring information that was not collected.
    """
    return all(record.get(c) is not None for c in RAW_COLUMNS) and (
        (record["packets_in"] or 0) + (record["packets_out"] or 0) > 0
    )


def compute_features(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[RAW_COLUMNS].astype("float64").copy()
    duration = df["flow_duration"].clip(lower=1e-6)
    pin, pout = df["packets_in"], df["packets_out"]
    total_packets = pin + pout
    total_bytes = df["bytes_in"] + df["bytes_out"]

    out = pd.DataFrame(index=df.index)
    out["flow_duration"] = df["flow_duration"]
    out["packets_in"] = pin
    out["packets_out"] = pout
    out["bytes_in"] = df["bytes_in"]
    out["bytes_out"] = df["bytes_out"]
    out["dst_port"] = df["dst_port"]
    out["dst_port_well_known"] = (df["dst_port"] < 1024).astype("float64")
    out["bytes_per_packet_in"] = np.where(pin > 0, df["bytes_in"] / pin.where(pin > 0, 1), 0.0)
    out["bytes_per_packet_out"] = np.where(pout > 0, df["bytes_out"] / pout.where(pout > 0, 1), 0.0)
    out["packets_per_second"] = total_packets / duration
    out["bytes_per_second"] = total_bytes / duration
    out["out_in_packet_ratio"] = pout / (pin + 1.0)
    out = out.replace([np.inf, -np.inf], np.nan)
    return out[FEATURE_COLUMNS]
