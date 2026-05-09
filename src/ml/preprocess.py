import pandas as pd
import re


class DataLoader:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.df = None

    def _parse_coords(self, coord_str):
        """Извлекает долготу и широту из строки (Decimal('...'), Decimal('...'))"""
        try:
            # Находим все числа в строке с помощью регулярки
            coords = re.findall(r"\d+\.\d+", coord_str)
            if len(coords) == 2:
                return float(coords[0]), float(coords[1])  # (lon, lat)
        except:
            return None, None
        return None, None

    def load_data(self):
        # Загружаем
        self.df = pd.read_csv(self.file_path)

        # Очистка названий от кавычек
        self.df['name'] = self.df['name'].str.strip(' "«»')

        # Парсим координаты в отдельные колонки
        self.df['lon'], self.df['lat'] = zip(*self.df['geolocation'].map(self._parse_coords))

        # --- ИСПРАВЛЕНИЕ ОШИБКИ 500 ---
        # 1. Удаляем строки, где координаты не распознались (NaN)
        self.df.dropna(subset=['lon', 'lat'], inplace=True)

        # 2. Сбрасываем индексы, чтобы не было "дырок" (ОЧЕНЬ ВАЖНО для матричных вычислений!)
        self.df.reset_index(drop=True, inplace=True)
        # ------------------------------

        # Заполняем пустые типы, если они есть
        self.df['type'] = self.df['type'].fillna('unknown')

        print(f"Загружено {len(self.df)} объектов с валидными координатами.")
        return self.df

    def get_regions(self):
        return sorted(self.df['region'].unique().tolist())