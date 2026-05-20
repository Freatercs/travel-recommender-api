import pandas as pd
from deep_translator import GoogleTranslator
import time
from tqdm import tqdm  # Красивый прогресс-бар в консоли


def translate_column(unique_values, description="Перевод"):
    """Переводит список уникальных значений с английского на русский"""
    translator = GoogleTranslator(source='en', target='ru')
    translations = {}

    print(f"\n--- Запуск перевода для: {description} ---")
    # tqdm показывает процент выполнения, скорость и расчетное время до конца
    for item in tqdm(unique_values):
        if pd.isna(item) or str(item).strip() == "":
            translations[item] = item
            continue
        try:
            # Небольшая пауза 0.2 сек, чтобы Google API не заблокировал за спам-запросы
            time.sleep(0.2)
            translated = translator.translate(str(item))
            translations[item] = translated
        except Exception as e:
            print(f"\n[Ошибка] Не удалось перевести '{item}': {e}")
            translations[item] = item  # В случае сбоя оставляем оригинальный текст

    return translations


def main():
    input_path = "../../data/raw/russian_tourist_attractions.csv"
    output_path = "../../data/raw/russian_tourist_attraction_ru.csv"

    print("Загрузка исходного датасета...")
    df = pd.read_csv(input_path)

    # Сюда собираем все столбцы, которые планируем локализовать
    columns_to_translate = ['name', 'type', 'region', 'locality']

    for col in columns_to_translate:
        if col in df.columns:
            # Извлекаем только уникальные значения, чтобы сэкономить время и не переводить дубли
            unique_values = df[col].dropna().unique()
            print(f"В столбце '{col}' найдено уникальных значений: {len(unique_values)}")

            # Запускаем перевод для уникального набора
            translated_dict = translate_column(unique_values, f"Столбец '{col}'")

            # Маппим (заменяем) английские значения на русские во всем датасете
            df[col] = df[col].map(translated_dict)
        else:
            print(f"⚠️ Предупреждение: Столбец '{col}' не найден в датасете. Пропускаем.")

    # Сохраняем результат в новый файл
    # utf-8-sig используется для того, чтобы Excel на Windows открывал файл сразу на русском, без иероглифов
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n🎉 Локализация завершена! Полностью русский датасет сохранен в: {output_path}")


if __name__ == "__main__":
    main()