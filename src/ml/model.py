import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import OneHotEncoder


class RecommenderEngine:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.similarity_matrix = None
        self.vectorized_df = None

    def build_model(self):
        """Создает матрицу сходства на основе типов и регионов"""
        # 1. Выбираем признаки для векторизации
        features = self.df[['type', 'region']]

        # 2. Применяем One-Hot Encoding (превращаем категории в колонки 0 и 1)
        encoder = OneHotEncoder()
        encoded_features = encoder.fit_transform(features)

        # 3. Вычисляем матрицу сходства (размер будет N x N, где N - кол-во объектов)
        self.similarity_matrix = cosine_similarity(encoded_features)

        print("Матрица сходства построена успешно.")

    def recommend(self, target_name: str, top_n: int = 5):
        """Находит top_n похожих объектов для заданного по имени"""
        if self.similarity_matrix is None:
            return []

        # Находим индекс объекта в датафрейме
        try:
            idx = self.df[self.df['name'] == target_name].index[0]
        except IndexError:
            return []

        # Получаем оценки сходства для этого объекта со всеми остальными
        sim_scores = list(enumerate(self.similarity_matrix[idx]))

        # Сортируем по убыванию сходства (пропуская сам объект - он на 1-м месте)
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)
        sim_scores = sim_scores[1:top_n + 1]

        # Получаем индексы и возвращаем названия/данные
        item_indices = [i[0] for i in sim_scores]
        return self.df.iloc[item_indices][['name', 'type', 'region', 'locality']].to_dict(orient='records')