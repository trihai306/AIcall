from __future__ import annotations

from collections import Counter
from functools import lru_cache
import json
import math
from pathlib import Path
import unicodedata


LABELS = ("profile", "product", "assistant")
LABEL_TO_TOOL = {
    "profile": "tra_ho_so_khach",
    "product": "tra_thong_tin_san_pham",
}
DEFAULT_MODEL = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "bankvn"
    / "router"
    / "router_nb_current.json"
)


def normalize(text: str) -> str:
    text = (text or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.split())


def features(text: str) -> Counter[str]:
    text = normalize(text)
    out: Counter[str] = Counter()
    padded = f"^{text}$"
    for n in (2, 3, 4, 5):
        for i in range(max(0, len(padded) - n + 1)):
            out[f"c{n}:{padded[i:i+n]}"] += 1
    words = text.split()
    for word in words:
        out[f"w:{word}"] += 2
    for a, b in zip(words, words[1:]):
        out[f"b:{a}_{b}"] += 2
    return out


def predict(model: dict, text: str) -> dict:
    feats = features(text)
    labels = tuple(model.get("labels") or LABELS)
    alpha = float(model.get("alpha") or 0.35)
    vocab_size = max(1, int(model.get("vocab_size") or 1))
    feature_totals = model.get("feature_totals") or {}
    feature_counts = model.get("feature_counts") or {}

    scores: dict[str, float] = {}
    prior = -math.log(max(1, len(labels)))
    for label in labels:
        counts = feature_counts.get(label) or {}
        denom = float(feature_totals.get(label) or 0) + alpha * vocab_size
        score = prior
        for feat, count in feats.items():
            score += count * math.log((float(counts.get(feat) or 0) + alpha) / denom)
        scores[label] = score

    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_label, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else top_score
    max_score = max(scores.values())
    exp_scores = {label: math.exp(score - max_score) for label, score in scores.items()}
    total = sum(exp_scores.values()) or 1.0
    probabilities = {label: value / total for label, value in exp_scores.items()}
    return {
        "label": top_label,
        "confidence": probabilities[top_label],
        "margin": top_score - second_score,
        "probabilities": probabilities,
    }


@lru_cache(maxsize=4)
def load_model(path: str) -> dict | None:
    model_path = Path(path)
    try:
        obj = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if obj.get("kind") != "bankvn_router_multinomial_nb":
        return None
    return obj


def classify(
    text: str,
    *,
    model_path: str | Path = DEFAULT_MODEL,
    min_confidence: float = 0.62,
    min_margin: float = 1.5,
) -> dict | None:
    model = load_model(str(model_path))
    if model is None:
        return None
    pred = predict(model, text)
    confident = (
        pred["confidence"] >= min_confidence
        and pred["margin"] >= min_margin
    )
    return {
        **pred,
        "confident": confident,
        "tool": LABEL_TO_TOOL.get(pred["label"]) if confident else None,
    }
