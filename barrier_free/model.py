"""가벼운 in-repo 위험 분류기.

외부 ML 의존성 없이 Pi 3B에서 돌아가는 MVP용 모델이다. 각 tree는 feature
부분집합을 보고 class centroid와의 거리를 비교하므로 Random Forest의
bagging/feature-subspace 아이디어를 단순화한 형태다.
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter

from . import labels


CLASSES = ("normal", "caution", "danger")


def training_rows_from_bundle(bundle: dict) -> list[dict]:
    """세션 bundle을 모델 학습 행으로 변환한다."""

    return labels.training_rows_from_bundle(bundle)


class TinyForestClassifier:
    """작은 feature-subspace centroid ensemble 분류기."""

    def __init__(self, tree_count: int = 9, seed: int = 0):
        if tree_count <= 0:
            raise ValueError("tree_count must be positive")
        self.tree_count = tree_count
        self.seed = seed
        self.feature_names: list[str] = []
        self.trees: list[dict] = []
        self.class_counts: dict[str, int] = {}

    def fit(self, rows: list[dict]) -> "TinyForestClassifier":
        if not rows:
            raise ValueError("training rows must not be empty")
        self.feature_names = sorted(rows[0]["features"])
        self.class_counts = dict(Counter(row["label"] for row in rows))
        rng = random.Random(self.seed)
        subset_size = max(2, int(math.sqrt(len(self.feature_names))))
        self.trees = []

        for _ in range(self.tree_count):
            subset = sorted(rng.sample(self.feature_names, subset_size))
            self.trees.append(
                {
                    "features": subset,
                    "centroids": _centroids(rows, subset),
                }
            )
        return self

    def predict(self, feature_row: dict) -> dict:
        if not self.trees:
            raise ValueError("model is not fitted")
        votes = []
        distances = []
        for tree in self.trees:
            label, distance = _nearest_class(feature_row, tree["features"], tree["centroids"])
            votes.append(label)
            distances.append(distance)

        counts = Counter(votes)
        prediction, vote_count = counts.most_common(1)[0]
        confidence = vote_count / len(self.trees)
        risk_score = _risk_score(prediction, confidence, min(distances) if distances else 0.0)
        return {
            "prediction": prediction,
            "confidence": round(confidence, 3),
            "risk_score": round(risk_score, 3),
        }

    def to_json(self) -> str:
        payload = {
            "tree_count": self.tree_count,
            "seed": self.seed,
            "feature_names": self.feature_names,
            "trees": self.trees,
            "class_counts": self.class_counts,
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "TinyForestClassifier":
        payload = json.loads(text)
        clf = cls(tree_count=payload["tree_count"], seed=payload["seed"])
        clf.feature_names = list(payload["feature_names"])
        clf.trees = list(payload["trees"])
        clf.class_counts = dict(payload["class_counts"])
        return clf


def evaluate(classifier: TinyForestClassifier, rows: list[dict]) -> dict:
    """학습/검증 행에 대한 confusion matrix와 recall을 계산한다."""

    matrix = {actual: {pred: 0 for pred in CLASSES} for actual in CLASSES}
    for row in rows:
        actual = row["label"]
        predicted = classifier.predict(row["features"])["prediction"]
        if actual in matrix and predicted in matrix[actual]:
            matrix[actual][predicted] += 1

    recall = {}
    for actual, predictions in matrix.items():
        total = sum(predictions.values())
        recall[actual] = 0.0 if total == 0 else round(predictions[actual] / total, 3)

    return {
        "confusion_matrix": matrix,
        "recall": recall,
        "training_rows": len(rows),
    }


def _centroids(rows: list[dict], feature_names: list[str]) -> dict:
    grouped: dict[str, list[dict]] = {label: [] for label in CLASSES}
    for row in rows:
        if row["label"] in grouped:
            grouped[row["label"]].append(row["features"])

    centroids = {}
    for label, feature_rows in grouped.items():
        if not feature_rows:
            continue
        centroids[label] = {
            name: sum(float(row[name]) for row in feature_rows) / len(feature_rows)
            for name in feature_names
        }
    return centroids


def _nearest_class(feature_row: dict, feature_names: list[str], centroids: dict) -> tuple[str, float]:
    best_label = "normal"
    best_distance = float("inf")
    for label, centroid in centroids.items():
        distance = math.sqrt(
            sum((float(feature_row[name]) - float(centroid[name])) ** 2 for name in feature_names)
        )
        if distance < best_distance:
            best_label = label
            best_distance = distance
    return best_label, best_distance


def _risk_score(prediction: str, confidence: float, distance: float) -> float:
    base = {"normal": 0.15, "caution": 0.55, "danger": 0.85}[prediction]
    distance_penalty = min(0.15, distance / 50.0)
    return max(0.0, min(1.0, base * confidence - distance_penalty))
