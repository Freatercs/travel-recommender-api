import pandas as pd

df = pd.read_csv("data/raw/russian_tourist_attractions.csv")

print("--- Уникальные типы объектов ---")
print(df['type'].value_counts())

print("\n--- Топ-10 регионов ---")
print(df['region'].value_counts().head(10))

print("\n--- Проверка пустых значений ---")
print(df.isnull().sum())