import numpy as np
import pandas as pd
import re
from typing import List, Optional, Set

from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import OneHotEncoder


class RecommenderEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.similarity_matrix = None
        self.encoder = OneHotEncoder()

    #Формула Гаверсинуса
    def _haversine_distance(self, lon1, lat1, lon2, lat2):
        # Перевод координат в радианы
        lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])

        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        km = 6371 * c
        return km
    #Матрица контентного сходства
    def build_model(self):
        # Выбираем признаки для One-Hot Encoding
        features = self.df[['type', 'region']]
        encoded_features = self.encoder.fit_transform(features)

        # Вычисляем базовую матрицу сходства
        self.similarity_matrix = cosine_similarity(encoded_features)
        print(f"Модель обучена. Размер матрицы сходства: {self.similarity_matrix.shape}")

    def _passes_filters(self, row, filter_city: str, filter_type: str) -> bool:
        candidate_city = str(row.get('locality', '')).strip()
        if filter_city != "Все города":
            if pd.isna(row.get('locality')) or candidate_city != filter_city.strip():
                return False

        candidate_type = str(row.get('type', '')).strip()
        if filter_type != "Все типы":
            if pd.isna(row.get('type')) or candidate_type != filter_type.strip():
                return False

        return True

    def _filtered_indices(self, filter_city: str = "Все города", filter_type: str = "Все типы"):
        return [
            i for i in range(len(self.df))
            if self._passes_filters(self.df.iloc[i], filter_city, filter_type)
        ]

    @staticmethod
    def _clean_float(val):
        if pd.isna(val) or val is None:
            return 0.0
        if isinstance(val, str):
            numbers = re.findall(r"[-+]?\d*\.\d+|\d+", val)
            if numbers:
                return float(numbers[0])
            return 0.0
        try:
            f_val = float(val)
            return f_val if (pd.notna(f_val) and not np.isinf(f_val)) else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _format_row(self, idx: int, score: float = 0.0, dist: float = 0.0) -> dict:
        row = self.df.iloc[idx]

        raw_lat = row.get('lat')
        raw_lon = row.get('lon')
        safe_lat = 0.0
        safe_lon = 0.0

        if isinstance(raw_lat, (tuple, list)) and len(raw_lat) >= 2:
            safe_lat = self._clean_float(raw_lat[0])
            safe_lon = self._clean_float(raw_lat[1])
        elif isinstance(raw_lat, str) and "(" in raw_lat:
            parts = re.findall(r"[-+]?\d*\.\d+|\d+", raw_lat)
            if len(parts) >= 2:
                safe_lat = float(parts[0])
                safe_lon = float(parts[1])
        else:
            safe_lat = self._clean_float(raw_lat)
            safe_lon = self._clean_float(raw_lon)

        safe_dist = 0.0
        if pd.notna(dist) and not np.isinf(dist):
            try:
                safe_dist = round(float(dist), 2)
            except (TypeError, ValueError):
                pass

        safe_score = 0.0
        if pd.notna(score) and not np.isinf(score):
            try:
                safe_score = round(float(score), 4)
            except (TypeError, ValueError):
                pass

        raw_locality = row.get('locality')
        if pd.isna(raw_locality) or raw_locality is None or str(raw_locality).lower() == 'null':
            safe_locality = ""
        else:
            safe_locality = str(raw_locality)

        return {
            "name": row['name'],
            "type": row['type'],
            "region": row['region'],
            "locality": safe_locality,
            "lat": safe_lat,
            "lon": safe_lon,
            "distance_km": safe_dist,
            "confidence_score": safe_score,
        }

    def _valid_coord_indices(self, indices: List[int]) -> List[int]:
        valid = []
        for idx in indices:
            row = self.df.iloc[idx]
            lat, lon = row.get("lat"), row.get("lon")
            if pd.notna(lat) and pd.notna(lon) and float(lat) != 0.0 and float(lon) != 0.0:
                valid.append(idx)
        return valid

    def _median_center(self, indices: List[int]) -> tuple:
        lats = [float(self.df.iloc[i]["lat"]) for i in indices]
        lons = [float(self.df.iloc[i]["lon"]) for i in indices]
        return float(np.median(lats)), float(np.median(lons))

    def _filter_near_center(
        self,
        indices: List[int],
        center_lat: float,
        center_lon: float,
        max_radius_km: float,
    ) -> List[int]:
        return [
            idx for idx in indices
            if self._haversine_distance(
                center_lon,
                center_lat,
                float(self.df.iloc[idx]["lon"]),
                float(self.df.iloc[idx]["lat"]),
            ) <= max_radius_km
        ]

    def _filter_city_core_candidates(
        self,
        candidates: List[int],
        min_required: int,
        preferred_radius_km: float = 30.0,
    ) -> tuple:
        if not candidates:
            return [], preferred_radius_km

        med_lat, med_lon = self._median_center(candidates)
        radii = [preferred_radius_km]
        for extra in (50.0, 80.0):
            if extra not in radii:
                radii.append(extra)

        for radius in radii:
            core = self._filter_near_center(candidates, med_lat, med_lon, radius)
            if len(core) >= min_required:
                return core, radius

        return candidates, radii[-1]

    def _sample_diverse_indices(
        self,
        candidates: List[int],
        top_n: int,
        seed: Optional[int] = None,
    ) -> List[int]:
        if not candidates or top_n <= 0:
            return []

        rng = np.random.default_rng(seed)
        shuffled = candidates.copy()
        rng.shuffle(shuffled)

        selected = []
        used_types = set()

        for idx in shuffled:
            if len(selected) >= top_n:
                break
            row = self.df.iloc[idx]
            obj_type = str(row.get("type", "")).strip()
            if obj_type not in used_types or len(used_types) < 3:
                selected.append(idx)
                used_types.add(obj_type)

        if len(selected) < top_n:
            for idx in shuffled:
                if idx not in selected:
                    selected.append(idx)
                if len(selected) >= top_n:
                    break

        return selected[:top_n]

    def _order_route_nearest_neighbor(self, indices: List[int]) -> List[int]:
        if len(indices) <= 1:
            return indices

        cen_lat, cen_lon = self._median_center(indices)

        remaining = indices.copy()
        start = min(
            remaining,
            key=lambda i: self._haversine_distance(
                cen_lon, cen_lat,
                float(self.df.iloc[i]["lon"]), float(self.df.iloc[i]["lat"]),
            ),
        )
        ordered = [start]
        remaining.remove(start)
        current = start

        while remaining:
            nxt = min(
                remaining,
                key=lambda i: self._haversine_distance(
                    float(self.df.iloc[current]["lon"]),
                    float(self.df.iloc[current]["lat"]),
                    float(self.df.iloc[i]["lon"]),
                    float(self.df.iloc[i]["lat"]),
                ),
            )
            ordered.append(nxt)
            remaining.remove(nxt)
            current = nxt

        return ordered

    def _split_indices_by_days(self, indices: List[int], days: int) -> List[List[int]]:
        if days <= 1 or len(indices) <= 1:
            return [indices]

        cen_lat, cen_lon = self._median_center(indices)

        def angle(idx: int) -> float:
            lat = float(self.df.iloc[idx]["lat"])
            lon = float(self.df.iloc[idx]["lon"])
            return float(np.arctan2(lat - cen_lat, lon - cen_lon))

        sorted_idx = sorted(indices, key=angle)
        chunk_size, remainder = divmod(len(sorted_idx), days)

        chunks = []
        pos = 0
        for day in range(days):
            size = chunk_size + (1 if day < remainder else 0)
            chunk = sorted_idx[pos: pos + size]
            pos += size
            if chunk:
                chunks.append(chunk)

        return chunks

    #Случайная подборка объектов
    def discover_diverse(
        self,
        top_n: int = 5,
        filter_city: str = "Все города",
        filter_type: str = "Все типы",
        seed: Optional[int] = None,
    ):
        candidates = self._valid_coord_indices(
            self._filtered_indices(filter_city, filter_type)
        )
        if not candidates:
            return []

        selected = self._sample_diverse_indices(candidates, top_n, seed)
        return [self._format_row(idx) for idx in selected]

    #План поездки
    def plan_trip(
        self,
        city: str,
        days: int = 1,
        points_per_day: int = 4,
        filter_type: str = "Все типы",
        seed: Optional[int] = None,
        city_radius_km: float = 30.0,
    ) -> dict:
        if city == "Все города" or not str(city).strip():
            return {"error": "Выберите конкретный город для планирования маршрута"}

        days = max(1, min(int(days), 7))
        points_per_day = max(2, min(int(points_per_day), 8))
        total_needed = days * points_per_day
        city_radius_km = max(5.0, min(float(city_radius_km), 100.0))

        raw_candidates = self._valid_coord_indices(
            self._filtered_indices(city, filter_type)
        )
        excluded_outliers = 0
        candidates, radius_used = self._filter_city_core_candidates(
            raw_candidates,
            min_required=total_needed,
            preferred_radius_km=city_radius_km,
        )
        excluded_outliers = len(raw_candidates) - len(candidates)

        if len(candidates) < days:
            return {
                "error": (
                    f"В городе «{city}» недостаточно достопримечательностей "
                    f"в радиусе {radius_used:.0f} км от центра "
                    f"(найдено {len(candidates)}, нужно минимум {days}). "
                    f"Попробуйте увеличить радиус города."
                )
            }

        total_pick = min(total_needed, len(candidates))
        selected = self._sample_diverse_indices(candidates, total_pick, seed)
        n_days = min(days, len(selected))
        day_groups = self._split_indices_by_days(selected, n_days)

        schedule = []
        total_distance = 0.0

        center_lat, center_lon = self._median_center(selected)

        for day_num, day_indices in enumerate(day_groups):
            ordered = self._order_route_nearest_neighbor(day_indices)
            stops = []
            day_distance = 0.0

            for order, idx in enumerate(ordered, start=1):
                leg = 0.0
                if order > 1:
                    prev = ordered[order - 2]
                    leg = self._haversine_distance(
                        float(self.df.iloc[prev]["lon"]),
                        float(self.df.iloc[prev]["lat"]),
                        float(self.df.iloc[idx]["lon"]),
                        float(self.df.iloc[idx]["lat"]),
                    )
                    day_distance += leg

                stop = self._format_row(idx)
                stop["order"] = order
                stop["leg_distance_km"] = round(leg, 2)
                stop["distance_from_center_km"] = round(
                    self._haversine_distance(
                        center_lon,
                        center_lat,
                        float(self.df.iloc[idx]["lon"]),
                        float(self.df.iloc[idx]["lat"]),
                    ),
                    2,
                )
                stops.append(stop)

            total_distance += day_distance
            schedule.append({
                "day": day_num + 1,
                "stops_count": len(stops),
                "distance_km": round(day_distance, 2),
                "stops": stops,
            })

        schedule.sort(key=lambda d: d["day"])

        return {
            "city": city,
            "days": len(schedule),
            "points_per_day": points_per_day,
            "filter_type": filter_type,
            "city_radius_km": round(radius_used, 1),
            "excluded_outliers": excluded_outliers,
            "total_stops": sum(d["stops_count"] for d in schedule),
            "total_distance_km": round(total_distance, 2),
            "schedule": schedule,
        }

    #Персональные рекомендации
    def recommend_personalized(
        self,
        anchor_names: list,
        top_n: int = 5,
        distance_weight: float = 0.3,
        filter_city: str = "Все города",
        filter_type: str = "Все типы",
        exclude_names: Optional[Set[str]] = None,
    ):
        exclude = set(exclude_names or set())

        if not anchor_names:
            return self.discover_diverse(
                top_n=top_n,
                filter_city=filter_city,
                filter_type=filter_type,
            )

        scored = {}
        per_anchor = max(2, (top_n * 2) // len(anchor_names))

        for anchor in anchor_names:
            recs = self.recommend(
                anchor,
                top_n=per_anchor,
                distance_weight=distance_weight,
                filter_city=filter_city,
                filter_type=filter_type,
            )
            for rec in recs:
                name = rec["name"]
                if name in exclude or name in anchor_names:
                    continue
                score = rec.get("confidence_score", 0.0)
                if name not in scored or score > scored[name][1]:
                    scored[name] = (rec, score)

        if not scored:
            return self.discover_diverse(
                top_n=top_n,
                filter_city=filter_city,
                filter_type=filter_type,
            )

        ranked = sorted(scored.values(), key=lambda item: item[1], reverse=True)[:top_n]
        return [rec for rec, _ in ranked]

    #Отели поблизости
    def find_nearby_hotels(self, hotels_df, target_lat, target_lon, radius_km=5.0):
        nearby = []

        for _, hotel in hotels_df.iterrows():
            dist = self._haversine_distance(target_lon, target_lat, hotel['lon'], hotel['lat'])

            if dist <= radius_km:
                nearby.append({
                    "name": hotel['name'],
                    "address": hotel['address'],
                    "distance_km": round(dist, 2),
                    "website": hotel['website'],
                    "lat": hotel['lat'],
                    "lon": hotel['lon']
                })

        # Сортируем: сначала самые близкие
        return sorted(nearby, key=lambda x: x['distance_km'])

    #Гибридная рекомендация
    def recommend(self, target_name: str, top_n: int = 5, distance_weight: float = 0.3,
                  filter_city: str = "Все города", filter_type: str = "Все типы"):
        if self.similarity_matrix is None:
            return []

        target_name_clean = target_name.strip().lower()
        try:
            temp_names = self.df['name'].str.lower().str.replace(r'[^\w\s]', '', regex=True)
            target_name_clean = re.sub(r'[^\w\s]', '', target_name_clean)
            target_idx = self.df[temp_names == target_name_clean].index[0]
        except (IndexError, KeyError):
            print(f"Объект '{target_name}' не найден в базе.")
            return []

        # Координаты целевого объекта
        t_lon = self.df.iloc[target_idx]['lon']
        t_lat = self.df.iloc[target_idx]['lat']

        # Получение базовых скоров сходства из матрицы
        content_scores = self.similarity_matrix[target_idx]

        hybrid_scores = []
        for i in range(len(self.df)):
            if i == target_idx:
                continue

            row_candidate = self.df.iloc[i]

            if not self._passes_filters(row_candidate, filter_city, filter_type):
                continue

            # Расчет показателей для объектов, прошедших фильтрацию
            sim_score = content_scores[i]
            dist = self._haversine_distance(t_lon, t_lat, row_candidate['lon'], row_candidate['lat'])
            geo_score = np.exp(-dist / 500)

            # Итоговая формула
            final_score = (1 - distance_weight) * sim_score + distance_weight * geo_score

            hybrid_scores.append((i, final_score, dist))

        # Сортировка по финальному скору
        hybrid_scores = sorted(hybrid_scores, key=lambda x: x[1], reverse=True)
        top_indices = hybrid_scores[:top_n]

        return [self._format_row(idx, score, dist) for idx, score, dist in top_indices]