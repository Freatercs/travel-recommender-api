import pandas as pd
import re


class DataLoader:
    def __init__(self, attractions_path, hotels_path):
        self.attractions_path = attractions_path
        self.hotels_path = hotels_path

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

    def load_attractions(self):
        # Загружаем
        self.df = pd.read_csv(self.attractions_path)

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

    def load_hotels(self):
        # Читаем Excel
        df = pd.read_excel(self.hotels_path)

        # 1. Базовая очистка: переименовываем и оставляем только нужное
        df = df.rename(columns={
            'Название': 'name',
            'X': 'lon',
            'Y': 'lat',
            'Населенный Пункт': 'city',
            'Адрес': 'address',
            'Сайт': 'website'
        })

        # 2. Удаляем записи, где нет координат (без них поиск невозможен)
        df = df.dropna(subset=['lat', 'lon'])

        # 3. Приводим координаты к чистому float (на случай, если там строки)
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')

        # 4. Заполняем пустоты в строковых полях, чтобы JSON не падал
        df['website'] = df['website'].fillna('Сайт не указан')
        df['address'] = df['address'].fillna('Адрес не указан')
        df['city'] = df['city'].fillna('Неизвестно')

        # 5. Сбрасываем индексы
        df = df.reset_index(drop=True)

        print(f"✅ База отелей загружена: {len(df)} объектов.")
        return df[['name', 'city', 'lat', 'lon', 'address', 'website']]