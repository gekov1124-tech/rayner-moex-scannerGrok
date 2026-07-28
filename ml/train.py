"""Train simple classifier for setup success probability."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT / "ml" / "artifacts"
MODEL_PATH = MODEL_DIR / "model.json"


def _softmax_fit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, steps: int = 400, lr: float = 0.05):
    """
    Lightweight logistic regression (no sklearn required).
    Works offline on Railway/small VMs.
    """
    n, d = X.shape
    # standardize
    mu = X.mean(axis=0)
    sigma = X.std(axis=0)
    sigma[sigma < 1e-8] = 1.0
    Xs = (X - mu) / sigma
    w = np.zeros(d)
    b = 0.0
    for _ in range(steps):
        z = Xs @ w + b
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
        err = p - y
        grad_w = (Xs.T @ err) / n + l2 * w
        grad_b = float(err.mean())
        w -= lr * grad_w
        b -= lr * grad_b
    return {"w": w.tolist(), "b": float(b), "mu": mu.tolist(), "sigma": sigma.tolist()}


def _predict_proba(model: dict, X: np.ndarray) -> np.ndarray:
    mu = np.array(model["mu"])
    sigma = np.array(model["sigma"])
    w = np.array(model["w"])
    b = float(model["b"])
    Xs = (X - mu) / sigma
    z = Xs @ w + b
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def train_model(
    X: np.ndarray,
    y: np.ndarray,
    save_path: Path = MODEL_PATH,
) -> Dict[str, Any]:
    if len(y) < 10:
        raise ValueError(f"Need at least 10 labeled samples, got {len(y)}")
    if len(np.unique(y)) < 2:
        raise ValueError("Need both profitable and losing examples to train")

    # time-ish split: last 20% as holdout (rows already roughly chronological for backtest)
    n = len(y)
    cut = max(int(n * 0.8), n - max(5, n // 5))
    Xtr, Xte = X[:cut], X[cut:]
    ytr, yte = y[:cut], y[cut:]
    if len(yte) < 3:
        Xtr, Xte, ytr, yte = X, X, y, y

    model = _softmax_fit(Xtr, ytr.astype(float))
    proba = _predict_proba(model, Xte)
    pred = (proba >= 0.5).astype(int)
    acc = float((pred == yte).mean()) if len(yte) else 0.0
    # baseline
    base = float(ytr.mean())
    meta = {
        "n_train": int(len(ytr)),
        "n_test": int(len(yte)),
        "test_accuracy": round(acc, 3),
        "train_pos_rate": round(base, 3),
        "feature_names": __import__("ml.features", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES,
    }
    payload = {"model": model, "meta": meta}
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def load_model(path: Path = MODEL_PATH) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def predict_proba(model_payload: dict, X: np.ndarray) -> np.ndarray:
    return _predict_proba(model_payload["model"], X)
