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

        # Парсим координаты в отдельные колонки для удобства расчетов
        self.df['lon'], self.df['lat'] = zip(*self.df['geolocation'].map(self._parse_coords))

        # Заполняем пустые типы, если они есть
        self.df['type'] = self.df['type'].fillna('unknown')

        print(f"Загружено {len(self.df)} объектов.")
        return self.df

    def get_regions(self):
        return sorted(self.df['region'].unique().tolist())