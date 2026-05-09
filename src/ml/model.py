import numpy as np
import pandas as pd
import re
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import OneHotEncoder


class RecommenderEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.similarity_matrix = None
        self.encoder = OneHotEncoder()

    def _haversine_distance(self, lon1, lat1, lon2, lat2):
        """
        Вычисляет расстояние в км между двумя точками на Земле.
        Используется для корректировки рекомендаций по географии.
        """
        # Перевод координат в радианы
        lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])

        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        km = 6371 * c
        return km

    def build_model(self):
        """
        Создает матрицу контентного сходства на основе типа и региона.
        """
        # Выбираем признаки для One-Hot Encoding
        features = self.df[['type', 'region']]

        # Обучаем энкодер и трансформируем признаки в бинарные векторы
        encoded_features = self.encoder.fit_transform(features)

        # Вычисляем базовую матрицу сходства (Cosine Similarity)
        self.similarity_matrix = cosine_similarity(encoded_features)
        print(f"Модель обучена. Размер матрицы сходства: {self.similarity_matrix.shape}")

    def recommend(self, target_name: str, top_n: int = 5, distance_weight: float = 0.3):
        """
        Гибридная рекомендация: учитывает сходство типов и географическую близость.

        :param target_name: Название объекта, для которого ищем похожие
        :param top_n: Количество рекомендаций
        :param distance_weight: Вес географической близости (от 0 до 1)
        """
        if self.similarity_matrix is None:
            return []

        # Очищаем входящее имя для более гибкого поиска
        target_name_clean = target_name.strip().lower()
        # 1. Поиск индекса целевого объекта
        try:
            # Создаем временную серию с очищенными именами для поиска
            # .str.replace(r'[^\w\s]', '', regex=True) уберет кавычки и знаки препинания
            temp_names = self.df['name'].str.lower().str.replace(r'[^\w\s]', '', regex=True)
            target_name_clean = re.sub(r'[^\w\s]', '', target_name_clean)

            target_idx = self.df[temp_names == target_name_clean].index[0]
        except (IndexError, KeyError):
            print(f"Объект '{target_name}' не найден в базе.")
            return []

        # Координаты целевого объекта
        t_lon = self.df.iloc[target_idx]['lon']
        t_lat = self.df.iloc[target_idx]['lat']

        # 2. Получение базовых скоров сходства из матрицы
        content_scores = self.similarity_matrix[target_idx]

        # 3. Расчет гибридного показателя для каждого объекта
        hybrid_scores = []
        for i in range(len(self.df)):
            if i == target_idx:
                continue

            # Базовое сходство (тип/регион)
            sim_score = content_scores[i]

            # Географическое сходство (через расстояние)
            dist = self._haversine_distance(t_lon, t_lat, self.df.iloc[i]['lon'], self.df.iloc[i]['lat'])

            # Функция затухания: если dist=0, geo_score=1. Если dist=500км, geo_score ~ 0.36.
            geo_score = np.exp(-dist / 500)

            # Итоговая формула: взвешенная сумма
            # По умолчанию: 70% сходство категорий, 30% близость
            final_score = (1 - distance_weight) * sim_score + distance_weight * geo_score

            hybrid_scores.append((i, final_score, dist))

        # 4. Сортировка по финальному скору
        hybrid_scores = sorted(hybrid_scores, key=lambda x: x[1], reverse=True)
        top_indices = hybrid_scores[:top_n]

        # 5. Формирование результата
        results = []
        for idx, score, dist in top_indices:
            row = self.df.iloc[idx]

            # Защита от NaN
            safe_dist = 0.0 if pd.isna(dist) else round(float(dist), 2)
            safe_score = 0.0 if pd.isna(score) else round(float(score), 4)

            results.append({
                "name": row['name'],
                "type": row['type'],
                "region": row['region'],
                "lat": float(row['lat']),  # Добавляем для карты
                "lon": float(row['lon']),  # Добавляем для карты
                "distance_km": safe_dist,
                "confidence_score": safe_score
            })

        return results