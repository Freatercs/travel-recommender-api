import pandas as pd

# df = pd.read_csv("data/raw/russian_tourist_attractions.csv")
#
# print("--- Уникальные типы объектов ---")
# print(df['type'].value_counts())
#
# print("\n--- Топ-10 регионов ---")
# print(df['region'].value_counts().head(10))
#
# print("\n--- Проверка пустых значений ---")
# print(df.isnull().sum())
df_hotels = pd.read_excel("data/raw/russian-hotels.xlsx")

# Выводим названия всех колонок
print("Колонки в файле:")
print(df_hotels.columns.tolist())

# Выводим первую строчку, чтобы понять формат данных
pd.set_option('display.max_columns', None)
pd.set_option('display.expand_frame_repr', False)

df_hotels = pd.read_excel("data/raw/russian-hotels.xlsx")
print(df_hotels.head())