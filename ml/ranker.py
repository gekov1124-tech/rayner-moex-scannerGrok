"""Apply trained model to rank/filter rule-based setups."""

from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from strategies.base import Setup
from ml.features import features_matrix
from ml.train import load_model, predict_proba, MODEL_PATH


class SetupRanker:
    def __init__(
        self,
        model_path: Path = MODEL_PATH,
        mode: str = "rank",  # rank | filter | off
        min_probability: float = 0.5,
    ):
        self.mode = (mode or "off").lower()
        self.min_probability = float(min_probability)
        self.payload = load_model(model_path) if self.mode != "off" else None
        self.available = self.payload is not None

    def apply(
        self,
        setups: List[Setup],
        data: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> List[Setup]:
        if self.mode == "off" or not setups:
            return setups
        if not self.available:
            # no model yet — keep rule order
            for s in setups:
                s.ml_prob = 0.0
                s.ml_score = float(s.score or 0)
            return setups

        X = features_matrix(setups, data)
        proba = predict_proba(self.payload, X)
        for s, p in zip(setups, proba):
            s.ml_prob = float(round(p, 4))
            # blend rule score with ML probability
            s.ml_score = float(round(0.4 * float(s.score or 0) + 60.0 * p, 3))

        ranked = sorted(setups, key=lambda s: s.ml_prob, reverse=True)
        if self.mode == "filter":
            filtered = [s for s in ranked if s.ml_prob >= self.min_probability]
            # never drop everything on first model — keep top 3 if all filtered
            if not filtered and ranked:
                return ranked[: min(3, len(ranked))]
            return filtered
        return ranked


def get_ranker_from_config(cfg: dict) -> SetupRanker:
    ml = cfg.get("ml") or {}
    path = ml.get("model_path")
    model_path = Path(path) if path else MODEL_PATH
    if not model_path.is_absolute():
        model_path = Path(__file__).resolve().parent.parent / model_path
    return SetupRanker(
        model_path=model_path,
        mode=ml.get("mode", "off"),
        min_probability=float(ml.get("min_probability", 0.55)),
    )
