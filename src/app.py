import urllib.parse

import streamlit as st
import requests
import pandas as pd
import pydeck as pdk

# Настройка страницы
st.set_page_config(page_title="Travel Recommender", layout="wide")

st.title("🌍 Интеллектуальная система туристических рекомендаций")
st.markdown("Дипломный проект: разработка рекомендательной системы на основе гибридного сходства")

# URL твоего FastAPI сервера
API_URL = "http://127.0.0.1:8000"

st.sidebar.header("⚙️ Настройки поиска")

# Слайдер для радиуса отелей
# Параметры: заголовок, мин, макс, значение по умолчанию
hotel_radius = st.sidebar.slider(
    "Радиус поиска отелей (км)",
    min_value=1,
    max_value=30,
    value=5,
    step=1
)

# Можно также перенести туда настройки рекомендаций достопримечательностей
dist_weight = st.sidebar.slider("Вес географии (достопримечательности)", 0.0, 1.0, 0.3)
top_n = st.sidebar.number_input("Количество рекомендаций", 1, 20, 5)


def get_wiki_info(name):
    """Получает краткое описание и ссылку из Википедии"""
    # Кодируем название для URL
    encoded_name = urllib.parse.quote(name)
    url = f"https://ru.wikipedia.org/wiki/{encoded_name}"
    print(url)
    #https://en.wikipedia.org/wiki/Blagoveshchensk_State_Pedagogical_University
    #https://ru.wikipedia.org/wiki/Blagoveshchensk%20State%20Pedagogical%20University

    try:
        response = requests.get(url, timeout=5)  # Таймаут, чтобы не вешать приложение
        print(response.status_code)
        if response.status_code == 200:
            print(response.json())
            data = response.json()
            return {
                "summary": data.get("extract", "Описание отсутствует"),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page", "")
            }
    except:
        pass

    return {"summary": "Не удалось найти описание", "url": ""}

# Функция для получения списка имен (наш debug эндпоинт пригодился!)
@st.cache_data  # Кэшируем, чтобы не дергать API при каждом клике
def get_object_names():
    try:
        response = requests.get(f"{API_URL}/debug/names")
        if response.status_code == 200:
            return response.json()["sample_names"]
    except:
        return []
    return []


# Интерфейс
names = get_object_names()

if not names:
    st.error("Не удалось подключиться к API. Убедись, что uvicorn запущен!")
else:

    # Основной выбор
    selected_object = st.selectbox("Выберите достопримечательность:", names)

    # 1. Инициализируем хранилище в начале скрипта, если его еще нет
    if "recs" not in st.session_state:
        st.session_state.recs = None

    # 2. Обработка кнопки поиска
    if st.button("Найти похожие места"):
        with st.spinner('Алгоритм рассчитывает сходство...'):
            params = {"top_n": top_n, "distance_weight": dist_weight}
            response = requests.get(f"{API_URL}/recommend/{selected_object}", params=params)

            if response.status_code == 200:
                # Сохраняем результат в session_state
                st.session_state.recs = response.json()["recommendations"]
            else:
                st.error("Ошибка при получении данных")

    # 3. Отображаем данные, если они есть в памяти
    if st.session_state.recs:
        st.subheader("📍 Рекомендуемые достопримечательности")

        # Создаем DataFrame
        df_recs = pd.DataFrame(st.session_state.recs)

        # Обогащаем данные из Википедии
        # Чтобы не делать это при каждом нажатии кнопки, можно закешировать
        with st.spinner('Подгружаем информацию из Википедии...'):
            wiki_data = [get_wiki_info(name) for name in df_recs['name']]
            df_recs['Описание'] = [d['summary'] for d in wiki_data]
            df_recs['Википедия'] = [d['url'] for d in wiki_data]

        # Настраиваем отображение таблицы
        st.dataframe(
            df_recs[['name', 'type', 'Описание', 'Википедия']],
            column_config={
                "name": "Название",
                "type": "Тип",
                "Описание": st.column_config.TextColumn(
                    "Краткое описание",
                    width="large",
                    help="Данные из Wikipedia API"
                ),
                "Википедия": st.column_config.LinkColumn(
                    "Ссылка",
                    display_text="Читать в Wiki"
                ),
            },
            hide_index=True,
            width="stretch"
        )
    # В src/app.py после отображения таблицы достопримечательностей

    # --- БЛОК ПОИСКА ОТЕЛЕЙ ---
    if st.session_state.recs:
        st.divider()  # Визуальная черта для отделения блоков
        st.subheader("🏨 Поиск жилья поблизости")

        # 1. Выбор объекта из списка рекомендаций
        rec_names = [r['name'] for r in st.session_state.recs]
        selected_rec_name = st.selectbox("Выберите достопримечательность, чтобы найти отели рядом:", rec_names)

        # Находим полные данные выбранной достопримечательности (координаты)
        selected_rec = next(r for r in st.session_state.recs if r['name'] == selected_rec_name)

        # 2. Кнопка поиска с динамическим текстом
        if st.button(f"Найти отели в радиусе {hotel_radius} км"):
            with st.spinner(f'Ищем отели вокруг {selected_rec_name}...'):
                # Запрос к API
                params = {
                    "lat": selected_rec['lat'],
                    "lon": selected_rec['lon'],
                    "radius": float(hotel_radius)
                }
                h_response = requests.get(f"{API_URL}/hotels/near", params=params)

                if h_response.status_code == 200:
                    hotels = h_response.json().get("hotels", [])

                    if hotels:
                        st.success(f"Найдено объектов: {len(hotels)}")

                        # --- ТАБЛИЦА ---
                        df_hotels = pd.DataFrame(hotels)

                        # Подготовка таблицы для красивого вывода
                        df_to_show = df_hotels[['name', 'address', 'distance_km', 'website']].copy()
                        df_to_show.columns = ['Название', 'Адрес', 'Расстояние (км)', 'Сайт']
                        st.table(df_to_show)

                        # --- КАРТА С ДВУМЯ СЛОЯМИ ---
                        # Подготовка данных для карты
                        df_attractions = pd.DataFrame(st.session_state.recs)
                        df_grouped = df_attractions.groupby(['lat', 'lon']).agg({
                            'name': lambda x: '<br/>• '.join(x),  # Создаем список с буллитами
                            'type': 'first',
                            'region': 'first'
                        }).reset_index()

                        # Добавляем HTML для тултипа достопримечательностей
                        df_grouped['tooltip_text'] = '🏛️ <b>Достопримечательности:</b><br/>• ' + df_grouped['name']

                        df_hotels_map = pd.DataFrame(hotels)

                        # Добавляем HTML для тултипа отелей
                        df_hotels_map['tooltip_text'] = '🏨 <b>' + df_hotels_map['name'] + '</b><br/>📍 ' + df_hotels_map[
                            'address'] + '<br/>📏 ' + df_hotels_map['distance_km'].round(1).astype(str) + ' км'

                        # Слой достопримечательностей (красные точки)
                        attractions_layer = pdk.Layer(
                            "ScatterplotLayer",
                            data=df_grouped,
                            get_position=["lon", "lat"],
                            get_color=[220, 30, 0, 160],
                            get_radius=80,
                            radius_min_pixels=6,
                            pickable=True,
                            auto_highlight=True,
                        )

                        # Слой отелей (синие точки)
                        hotels_layer = pdk.Layer(
                            "ScatterplotLayer",
                            data=df_hotels_map,
                            get_position=["lon", "lat"],
                            get_color=[0, 120, 255, 200],
                            get_radius=50,
                            radius_min_pixels=6,
                            radius_max_pixels=15,
                            pickable=True,
                            auto_highlight=True,
                        )

                        # Настройка камеры (центрируемся на выбранном месте)
                        dynamic_zoom = 14 - (hotel_radius / 10)
                        view_state = pdk.ViewState(
                            latitude=selected_rec['lat'],
                            longitude=selected_rec['lon'],
                            zoom=max(dynamic_zoom, 10),
                            pitch=45,
                        )

                        # Отрисовка карты PyDeck с правильным tooltip
                        deck = pdk.Deck(
                            layers=[attractions_layer, hotels_layer],
                            initial_view_state=view_state,
                            map_style=None,
                            tooltip={
                                "html": "<div style='background-color: #2c3e50; padding: 8px; border-radius: 4px; max-width: 300px;'>"
                                        "{tooltip_text}"
                                        "</div>",
                                "style": {
                                    "color": "white",
                                    "backgroundColor": "rgba(0,0,0,0)",
                                    "fontSize": "12px"
                                }
                            }
                        )

                        st.pydeck_chart(deck)
                    else:
                        st.warning(
                            f"В радиусе {hotel_radius} км отелей не найдено. Попробуйте увеличить радиус в боковом меню.")
                else:
                    st.error("Ошибка API при поиске отелей.")