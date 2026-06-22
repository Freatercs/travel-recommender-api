"""
Оценка качества рекомендаций для экспериментальной главы диплома.

Критерий релевантности (экспертное правило на структуре датасета):
  объект релевантен якорю, если совпадают region и type, либо
  совпадает type и расстояние не больше max_distance_km.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set

import numpy as np
import pandas as pd

from src.ml.model import RecommenderEngine
from src.ml.preprocess import DataLoader


@dataclass
class AnchorMetrics:
    anchor_name: str
    relevant_count: int
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    ndcg_at_k: float
    avg_recommended_distance_km: float


@dataclass
class ModelEvaluation:
    model_name: str
    distance_weight: float
    k: int
    anchors_evaluated: int
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    ndcg_at_k: float
    avg_route_distance_km: float
    diversity_km: float


def build_relevant_set(
    engine: RecommenderEngine,
    anchor_idx: int,
    max_distance_km: float = 80.0,
) -> Set[int]:
    anchor = engine.df.iloc[anchor_idx]
    a_type = str(anchor.get("type", ""))
    a_region = str(anchor.get("region", ""))
    a_lat = float(anchor["lat"])
    a_lon = float(anchor["lon"])

    relevant = set()
    for idx in range(len(engine.df)):
        if idx == anchor_idx:
            continue
        row = engine.df.iloc[idx]
        same_type = str(row.get("type", "")) == a_type
        same_region = str(row.get("region", "")) == a_region
        dist = engine._haversine_distance(
            a_lon, a_lat, float(row["lon"]), float(row["lat"])
        )
        if (same_type and same_region) or (same_type and dist <= max_distance_km):
            relevant.add(idx)
    return relevant


def _precision_recall_f1(recommended: Set[int], relevant: Set[int]) -> tuple:
    if not recommended:
        return 0.0, 0.0, 0.0
    hits = len(recommended & relevant)
    precision = hits / len(recommended)
    recall = hits / len(relevant) if relevant else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _ndcg_at_k(recommended_indices: List[int], relevant: Set[int], k: int) -> float:
    dcg = 0.0
    for i, idx in enumerate(recommended_indices[:k]):
        rel = 1.0 if idx in relevant else 0.0
        dcg += rel / np.log2(i + 2)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / np.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def _avg_pairwise_distance_km(engine: RecommenderEngine, indices: List[int]) -> float:
    if len(indices) < 2:
        return 0.0
    dists = []
    for i in range(len(indices)):
        for j in range(i + 1, len(indices)):
            a, b = engine.df.iloc[indices[i]], engine.df.iloc[indices[j]]
            dists.append(
                engine._haversine_distance(
                    float(a["lon"]), float(a["lat"]),
                    float(b["lon"]), float(b["lat"]),
                )
            )
    return float(np.mean(dists))


def evaluate_anchor(
    engine: RecommenderEngine,
    anchor_idx: int,
    k: int = 5,
    distance_weight: float = 0.3,
    max_distance_km: float = 80.0,
    filter_city: str = "Все города",
    filter_type: str = "Все типы",
) -> Optional[AnchorMetrics]:
    anchor_name = engine.df.iloc[anchor_idx]["name"]
    relevant = build_relevant_set(engine, anchor_idx, max_distance_km=max_distance_km)
    if len(relevant) < 3:
        return None

    recs = engine.recommend(
        anchor_name,
        top_n=k,
        distance_weight=distance_weight,
        filter_city=filter_city,
        filter_type=filter_type,
    )
    if not recs:
        return None

    name_to_idx = {
        str(engine.df.iloc[i]["name"]).strip().lower(): i
        for i in range(len(engine.df))
    }
    recommended_indices = []
    distances = []
    anchor_row = engine.df.iloc[anchor_idx]
    for rec in recs:
        key = str(rec["name"]).strip().lower()
        if key in name_to_idx:
            idx = name_to_idx[key]
            recommended_indices.append(idx)
            distances.append(rec.get("distance_km", 0.0))

    if not recommended_indices:
        return None

    recommended_set = set(recommended_indices)
    precision, recall, f1 = _precision_recall_f1(recommended_set, relevant)
    ndcg = _ndcg_at_k(recommended_indices, relevant, k)

    return AnchorMetrics(
        anchor_name=anchor_name,
        relevant_count=len(relevant),
        precision_at_k=round(precision, 4),
        recall_at_k=round(recall, 4),
        f1_at_k=round(f1, 4),
        ndcg_at_k=round(ndcg, 4),
        avg_recommended_distance_km=round(float(np.mean(distances)), 2),
    )


def sample_anchor_indices(
    engine: RecommenderEngine,
    sample_size: int = 200,
    seed: int = 42,
    min_relevant: int = 5,
    max_distance_km: float = 80.0,
) -> List[int]:
    rng = np.random.default_rng(seed)
    candidates = list(range(len(engine.df)))
    rng.shuffle(candidates)

    selected = []
    for idx in candidates:
        if len(build_relevant_set(engine, idx, max_distance_km=max_distance_km)) >= min_relevant:
            selected.append(idx)
        if len(selected) >= sample_size:
            break
    return selected


def evaluate_model(
    engine: RecommenderEngine,
    anchor_indices: List[int],
    distance_weight: float,
    model_name: str,
    k: int = 5,
) -> ModelEvaluation:
    rows: List[AnchorMetrics] = []
    diversities: List[float] = []

    for idx in anchor_indices:
        m = evaluate_anchor(engine, idx, k=k, distance_weight=distance_weight)
        if m:
            rows.append(m)
            anchor_name = engine.df.iloc[idx]["name"]
            recs = engine.recommend(
                anchor_name, top_n=k, distance_weight=distance_weight
            )
            name_to_idx = {
                str(engine.df.iloc[i]["name"]).strip().lower(): i
                for i in range(len(engine.df))
            }
            rec_indices = [
                name_to_idx[str(r["name"]).strip().lower()]
                for r in recs
                if str(r["name"]).strip().lower() in name_to_idx
            ]
            diversities.append(_avg_pairwise_distance_km(engine, rec_indices))

    if not rows:
        return ModelEvaluation(
            model_name=model_name,
            distance_weight=distance_weight,
            k=k,
            anchors_evaluated=0,
            precision_at_k=0.0,
            recall_at_k=0.0,
            f1_at_k=0.0,
            ndcg_at_k=0.0,
            avg_route_distance_km=0.0,
            diversity_km=0.0,
        )

    return ModelEvaluation(
        model_name=model_name,
        distance_weight=distance_weight,
        k=k,
        anchors_evaluated=len(rows),
        precision_at_k=round(float(np.mean([r.precision_at_k for r in rows])), 4),
        recall_at_k=round(float(np.mean([r.recall_at_k for r in rows])), 4),
        f1_at_k=round(float(np.mean([r.f1_at_k for r in rows])), 4),
        ndcg_at_k=round(float(np.mean([r.ndcg_at_k for r in rows])), 4),
        avg_route_distance_km=round(
            float(np.mean([r.avg_recommended_distance_km for r in rows])), 2
        ),
        diversity_km=round(float(np.mean(diversities)), 2) if diversities else 0.0,
    )


def evaluate_trip_planner(
    engine: RecommenderEngine,
    cities: List[str],
    days: int = 2,
    points_per_day: int = 4,
    city_radius_km: float = 30.0,
) -> Dict[str, float]:
    day_distances = []
    leg_distances = []
    outlier_legs = 0
    total_legs = 0

    for city in cities:
        plan = engine.plan_trip(
            city=city,
            days=days,
            points_per_day=points_per_day,
            city_radius_km=city_radius_km,
            seed=42,
        )
        if plan.get("error"):
            continue
        for day_block in plan.get("schedule", []):
            day_distances.append(day_block["distance_km"])
            for stop in day_block["stops"]:
                leg = stop.get("leg_distance_km", 0.0)
                if stop.get("order", 1) > 1:
                    total_legs += 1
                    leg_distances.append(leg)
                    if leg > 15.0:
                        outlier_legs += 1

    return {
        "cities_tested": len(cities),
        "avg_day_route_km": round(float(np.mean(day_distances)), 2) if day_distances else 0.0,
        "avg_leg_km": round(float(np.mean(leg_distances)), 2) if leg_distances else 0.0,
        "max_leg_km": round(float(np.max(leg_distances)), 2) if leg_distances else 0.0,
        "outlier_leg_rate": round(outlier_legs / total_legs, 4) if total_legs else 0.0,
    }


def run_full_evaluation(
    attractions_path: str = "data/raw/russian_tourist_attraction_ru.csv",
    hotels_path: str = "data/raw/russian-hotels.xlsx",
    sample_size: int = 200,
    k: int = 5,
    seed: int = 42,
) -> dict:
    loader = DataLoader(attractions_path, hotels_path)
    df = loader.load_attractions()
    engine = RecommenderEngine(df)
    engine.build_model()

    anchors = sample_anchor_indices(engine, sample_size=sample_size, seed=seed)

    models = [
        ("content_only", 0.0),
        ("hybrid_balanced", 0.3),
        ("geo_priority", 0.6),
    ]
    model_results = [
        asdict(evaluate_model(engine, anchors, weight, name, k=k))
        for name, weight in models
    ]

    cities = (
        df["locality"]
        .dropna()
        .astype(str)
        .str.strip()
        .value_counts()
        .head(8)
        .index.tolist()
    )
    trip_metrics = evaluate_trip_planner(engine, cities)

    return {
        "dataset": {
            "attractions_total": len(df),
            "anchors_sampled": len(anchors),
            "k": k,
            "seed": seed,
        },
        "relevance_rule": (
            "Релевантны объекты с тем же type и region, либо тем же type "
            "в радиусе 80 км от якоря."
        ),
        "recommendation_models": model_results,
        "trip_planner": trip_metrics,
    }


def save_evaluation_report(
    output_dir: str = "docs/experiments",
    **kwargs,
) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = run_full_evaluation(**kwargs)
    json_path = output_path / "metrics_results.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    rows = results["recommendation_models"]
    pd.DataFrame(rows).to_csv(output_path / "metrics_comparison.csv", index=False)

    return json_path
