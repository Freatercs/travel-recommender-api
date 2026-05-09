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
    # Боковая панель с настройками
    st.sidebar.header("Настройки алгоритма")
    dist_weight = st.sidebar.slider("Вес географии (distance weight)", 0.0, 1.0, 0.3)
    top_n = st.sidebar.number_input("Количество рекомендаций", 1, 10, 5)

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
        df_recs = pd.DataFrame(st.session_state.recs)

        # Таблица
        st.subheader(f"Результаты для: {selected_object}")
        st.table(df_recs[['name', 'type', 'region', 'distance_km', 'confidence_score']])

        # Карта
        if st.button("Показать на карте"):
            if 'lat' in df_recs.columns and 'lon' in df_recs.columns:
                # Настраиваем визуализацию слоя с точками
                layer = pdk.Layer(
                    "ScatterplotLayer",
                    df_recs,
                    get_position=["lon", "lat"],
                    get_color=[255, 0, 0, 200],  # Сделаем чуть ярче (красный)
                    get_radius=30,  # Радиус 30 метров (золотая середина)
                    radius_min_pixels=5,  # Минимальный размер в пикселях (чтобы не исчезали при зуме)
                    radius_max_pixels=15,  # Максимальный размер в пикселях
                    pickable=True,
                )

                # Настраиваем вид камеры (центрируемся на первой рекомендации)
                view_state = pdk.ViewState(
                    latitude=df_recs["lat"].mean(),
                    longitude=df_recs["lon"].mean(),
                    zoom=10,
                    pitch=0,
                )

                # Отрисовываем карту с подсказками (tooltips)
                st.pydeck_chart(pdk.Deck(
                    layers=[layer],
                    initial_view_state=view_state,
                    tooltip={"text": "{name}\nТип: {type}\nРегион: {region}"}  # Вот тут магия подписей
                ))
            else:
                st.warning("В данных отсутствуют координаты.")