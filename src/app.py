from collections import defaultdict
from typing import Optional, Tuple

import pandas as pd
import streamlit as st
import requests
import urllib.parse
import pydeck as pdk

st.set_page_config(page_title="Travel Recommender", layout="wide")

st.title("Интеллектуальная система туристических рекомендаций")
st.subheader("Настройте параметры поиска:")
df_all = pd.read_csv("data/raw/russian_tourist_attraction_ru.csv")

unique_cities = df_all["locality"].dropna().unique().tolist()
unique_cities = [c for c in unique_cities if str(c).strip() != ""]
city_options = ["Все города"] + sorted(unique_cities)

unique_types = df_all["type"].dropna().unique().tolist()
unique_types = [t for t in unique_types if str(t).strip() != ""]
type_options = ["Все типы"] + sorted(unique_types)


def _option_index(options: list, value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _init_applied_filters():
    defaults = {
        "applied_city": "Все города",
        "applied_type": "Все типы",
        "applied_top_n": 5,
        "applied_dist_weight": 0.3,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_applied_filters()

with st.form("main_filters", clear_on_submit=False):
    col_filter1, col_filter2 = st.columns(2)
    with col_filter1:
        form_city = st.selectbox(
            "🎯 Выберите город/локацию:",
            city_options,
            index=_option_index(city_options, st.session_state.applied_city),
        )
    with col_filter2:
        form_type = st.selectbox(
            "🏛️ Тип достопримечательности:",
            type_options,
            index=_option_index(type_options, st.session_state.applied_type),
        )
    apply_filters = st.form_submit_button("Применить фильтры", use_container_width=True)

if apply_filters:
    filters_changed = (
        form_city != st.session_state.applied_city
        or form_type != st.session_state.applied_type
    )
    st.session_state.applied_city = form_city
    st.session_state.applied_type = form_type
    if filters_changed and st.session_state.get("recs_source") != "anchor":
        st.session_state.recs = None
        st.session_state.discover_key = None
        st.session_state.hotels = None

selected_city = st.session_state.applied_city
selected_type = st.session_state.applied_type

st.caption(
    f"Активные фильтры: **{selected_city}** · **{selected_type}** "
    "(измените значения и нажмите «Применить фильтры»)"
)
# URL FastAPI сервера
API_URL = "http://127.0.0.1:8000"
HOTELS_PER_PAGE = 10

st.sidebar.header("⚙️ Настройки поиска")

# Слайдер для радиуса отелей (не влияет на рекомендации)
hotel_radius = st.sidebar.slider(
    "Радиус поиска отелей (км)",
    min_value=1,
    max_value=30,
    value=5,
    step=1,
)

with st.sidebar.form("rec_settings", clear_on_submit=False):
    st.markdown("**Рекомендации**")
    form_dist_weight = st.slider(
        "Вес географии (достопримечательности)",
        0.0,
        1.0,
        float(st.session_state.applied_dist_weight),
    )
    form_top_n = st.number_input(
        "Количество рекомендаций",
        1,
        20,
        int(st.session_state.applied_top_n),
    )
    apply_settings = st.form_submit_button("Применить настройки", use_container_width=True)

if apply_settings:
    settings_changed = (
        form_dist_weight != st.session_state.applied_dist_weight
        or int(form_top_n) != int(st.session_state.applied_top_n)
    )
    st.session_state.applied_dist_weight = form_dist_weight
    st.session_state.applied_top_n = int(form_top_n)
    if settings_changed and st.session_state.get("recs_source") != "anchor":
        st.session_state.recs = None
        st.session_state.discover_key = None
        st.session_state.hotels = None

dist_weight = st.session_state.applied_dist_weight
top_n = st.session_state.applied_top_n


def auth_headers() -> dict:
    token = st.session_state.get("access_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def _api_error_message(response) -> str:
    try:
        data = response.json()
        detail = data.get("detail", "Ошибка запроса")
        if isinstance(detail, list):
            return detail[0].get("msg", str(detail))
        return str(detail)
    except Exception:
        text = (response.text or "").strip()
        if text and text != "Internal Server Error":
            return text[:300]
        return f"Ошибка сервера (код {response.status_code}). Проверьте, что API запущен."


def api_register(email: str, password: str) -> Tuple[bool, str]:
    try:
        response = requests.post(
            f"{API_URL}/auth/register",
            json={"email": email, "password": password},
            timeout=15,
        )
        if response.status_code == 201:
            data = response.json()
            st.session_state.access_token = data["access_token"]
            st.session_state.user_email = data["user"]["email"]
            st.session_state.user_id = data["user"]["id"]
            return True, ""
        return False, _api_error_message(response)
    except Exception:
        return False, "Не удалось связаться с API"


def api_login(email: str, password: str) -> Tuple[bool, str]:
    try:
        response = requests.post(
            f"{API_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.access_token = data["access_token"]
            st.session_state.user_email = data["user"]["email"]
            st.session_state.user_id = data["user"]["id"]
            return True, ""
        return False, _api_error_message(response)
    except Exception:
        return False, "Не удалось связаться с API"


def api_logout():
    for key in (
        "access_token", "user_email", "user_id", "favorites",
        "logged_views", "recs", "recs_source", "discover_key", "personal_version",
    ):
        st.session_state.pop(key, None)


def load_favorites() -> set:
    try:
        response = requests.get(
            f"{API_URL}/interactions/favorites",
            headers=auth_headers(),
            timeout=15,
        )
        if response.status_code == 200:
            return set(response.json().get("favorites", []))
    except Exception:
        pass
    return set()


def api_toggle_favorite(name: str, is_favorite: bool) -> bool:
    try:
        if is_favorite:
            encoded = urllib.parse.quote(name)
            response = requests.delete(
                f"{API_URL}/interactions/favorite/{encoded}",
                headers=auth_headers(),
                timeout=15,
            )
            return response.status_code == 200
        response = requests.post(
            f"{API_URL}/interactions",
            headers=auth_headers(),
            json={"attraction_name": name, "event_type": "favorite"},
            timeout=15,
        )
        return response.status_code == 200
    except Exception:
        return False


def api_log_view(name: str):
    if name in st.session_state.get("logged_views", set()):
        return
    try:
        response = requests.post(
            f"{API_URL}/interactions",
            headers=auth_headers(),
            json={"attraction_name": name, "event_type": "view"},
            timeout=10,
        )
        if response.status_code == 200:
            st.session_state.logged_views.add(name)
    except Exception:
        pass


def fetch_personal(city: str, obj_type: str, n: int, distance_weight: float) -> Optional[list]:
    try:
        response = requests.get(
            f"{API_URL}/recommend/personal",
            headers=auth_headers(),
            params={
                "top_n": n,
                "filter_city": city,
                "filter_type": obj_type,
                "distance_weight": distance_weight,
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("recommendations", [])
    except Exception:
        pass
    return None


# --- Блок авторизации в сайдбаре ---
st.sidebar.divider()
st.sidebar.header("👤 Аккаунт")

if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "favorites" not in st.session_state:
    st.session_state.favorites = set()
if "logged_views" not in st.session_state:
    st.session_state.logged_views = set()
if "personal_version" not in st.session_state:
    st.session_state.personal_version = 0

is_logged_in = bool(st.session_state.access_token)

if is_logged_in:
    st.sidebar.success(f"Вы вошли: {st.session_state.get('user_email', '')}")
    st.session_state.favorites = load_favorites()
    if st.session_state.favorites:
        with st.sidebar.expander(f"⭐ Избранное ({len(st.session_state.favorites)})"):
            for fav in list(st.session_state.favorites)[:15]:
                st.caption(f"• {fav}")
    if st.sidebar.button("Выйти", use_container_width=True):
        api_logout()
        st.rerun()
else:
    auth_tab_login, auth_tab_register = st.sidebar.tabs(["Вход", "Регистрация"])
    with auth_tab_login:
        login_email = st.text_input("Email", key="login_email")
        login_password = st.text_input("Пароль", type="password", key="login_password")
        if st.button("Войти", key="btn_login", use_container_width=True):
            ok, err = api_login(login_email, login_password)
            if ok:
                st.session_state.recs = None
                st.session_state.recs_source = None
                st.session_state.discover_key = None
                st.rerun()
            st.error(err)
    with auth_tab_register:
        reg_email = st.text_input("Email ", key="reg_email")
        reg_password = st.text_input("Пароль (от 6 символов)", type="password", key="reg_password")
        if st.button("Зарегистрироваться", key="btn_register", use_container_width=True):
            ok, err = api_register(reg_email, reg_password)
            if ok:
                st.session_state.recs = None
                st.session_state.recs_source = None
                st.session_state.discover_key = None
                st.rerun()
            st.error(err)
    st.sidebar.caption("Войдите, чтобы получать рекомендации по избранному и просмотрам.")


def get_llm_info(name: str, locality: str = "") -> dict:
    """Описание и ссылка на карту (Nominatim + Яндекс Карты)."""
    search_query = f"{locality} {name}".strip()
    return get_llm_info_cached(search_query, locality)


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner=False)
def get_llm_info_cached(search_query: str, locality: str = "") -> dict:
    yandex_maps_url = f"https://yandex.ru/maps/?text={urllib.parse.quote(search_query)}"

    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": search_query,
            "format": "json",
            "addressdetails": 1,
            "limit": 1,
            "accept-language": "ru",
        }
        headers = {"User-Agent": "TravelRecommenderBot/1.0 (student_project@university.edu)"}
        response = requests.get(url, params=params, headers=headers, timeout=4)

        if response.status_code == 200:
            data = response.json()
            if data:
                result = data[0]
                address_info = result.get("address", {})

                road = address_info.get("road", "")
                house_number = address_info.get("house_number", "")
                city = address_info.get("city", address_info.get("town", locality))

                full_address = f"{city}"
                if road:
                    full_address += f", {road}"
                if house_number:
                    full_address += f", {house_number}"

                osm_class = result.get("class", "tourism")
                osm_type = result.get("type", "attraction")

                type_mapping = {
                    "historic": "Памятник истории",
                    "monument": "Монумент / Памятник",
                    "museum": "Музей",
                    "university": "Университет / Институт",
                    "college": "Колледж / Гимназия",
                    "church": "Храм / Церковь",
                    "place_of_worship": "Культовое сооружение",
                    "theatre": "Театр",
                    "castle": "Замок / Крепость",
                    "park": "Парк / Сквер",
                    "attraction": "Достопримечательность",
                }

                ru_type = type_mapping.get(osm_type, type_mapping.get(osm_class, "Достопримечательность"))
                summary = f"📍 {full_address} | 🏛️ Категория: {ru_type}"

                return {"summary": summary, "url": yandex_maps_url}

    except Exception as e:
        print(f"[OSM Error] Ошибка геокодирования для {search_query}: {e}")

    return {
        "summary": (
            f"📍 Локация: {locality if locality else 'Россия'} | "
            f"🏛️ Тип: Исторический объект. Подробный адрес и отзывы смотрите на картах."
        ),
        "url": yandex_maps_url,
    }


@st.cache_data
def get_object_names():
    try:
        response = requests.get(f"{API_URL}/debug/names")
        if response.status_code == 200:
            return response.json()["sample_names"]
    except Exception:
        return []
    return []


def enrich_recommendations(raw_recs: list) -> list:
    """Добавляет описание и ссылку на карту к списку рекомендаций."""
    df_recs = pd.DataFrame(raw_recs)
    llm_data = []
    for _, row in df_recs.iterrows():
        loc = row.get('locality', '')
        if pd.isna(loc) or str(loc).strip() == '' or str(loc).lower() == 'nan':
            reg = row.get('region', '')
            geo_context = reg if (pd.notna(reg) and str(reg).strip() != '') else ''
        else:
            geo_context = loc

        info = get_llm_info(row['name'], str(geo_context).strip())
        llm_data.append(info)

    df_recs['Описание'] = [d['summary'] for d in llm_data]
    df_recs['Ресурс'] = [d['url'] for d in llm_data]
    return df_recs.to_dict(orient="records")


def fetch_trip_plan(
    city: str,
    days: int,
    points_per_day: int,
    filter_type: str,
    city_radius_km: float = 30.0,
) -> Optional[dict]:
    try:
        response = requests.get(
            f"{API_URL}/trip/plan",
            params={
                "city": city,
                "days": days,
                "points_per_day": points_per_day,
                "filter_type": filter_type,
                "city_radius_km": city_radius_km,
            },
            timeout=30,
        )
        if response.status_code == 200:
            return response.json()
        st.error(_api_error_message(response))
    except Exception:
        st.error("Не удалось связаться с API для построения маршрута")
    return None


TRIP_DAY_COLORS = [
    [220, 53, 69, 220],
    [25, 135, 84, 220],
    [13, 110, 253, 220],
    [255, 193, 7, 220],
    [111, 66, 193, 220],
    [253, 126, 20, 220],
    [32, 201, 151, 220],
]


def render_trip_plan(plan: dict):
    radius_info = ""
    if plan.get("city_radius_km"):
        radius_info = f" · Радиус города: **{plan['city_radius_km']} км**"
    excluded = plan.get("excluded_outliers", 0)
    if excluded:
        radius_info += f" · Исключено далёких точек: **{excluded}**"

    st.caption(
        f"Город: **{plan['city']}** · "
        f"Дней: **{plan['days']}** · "
        f"Остановок: **{plan['total_stops']}** · "
        f"Суммарно по маршруту: **{plan['total_distance_km']} км**"
        f"{radius_info}"
    )

    for day_block in plan["schedule"]:
        day_num = day_block["day"]
        with st.expander(
            f"День {day_num} — {day_block['stops_count']} остановок, "
            f"~{day_block['distance_km']} км между точками",
            expanded=(day_num == 1),
        ):
            rows = []
            for stop in day_block["stops"]:
                rows.append({
                    "№": stop["order"],
                    "Название": stop["name"],
                    "Тип": stop["type"],
                    "От центра (км)": stop.get("distance_from_center_km", "—"),
                    "От пред. точки (км)": stop["leg_distance_km"],
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def _build_trip_tooltip(visits: list) -> str:
    """Формат строки: День N (остановка M) — название места."""
    visits_sorted = sorted(visits, key=lambda v: (v["day"], v["order"]))
    lines = []
    for visit in visits_sorted:
        lines.append(
            "<div style='margin-bottom:6px;font-size:13px;line-height:1.35;'>"
            f"<b>День {visit['day']}</b> (остановка {visit['order']}) — {visit['name']}"
            "</div>"
        )

    unique_types = {v["type"] for v in visits_sorted if v.get("type")}
    if len(unique_types) == 1:
        lines.append(
            f"<div style='font-size:12px;opacity:0.9;margin-top:2px;'>"
            f"🏛️ {unique_types.pop()}</div>"
        )

    return "".join(lines)


TRIP_MAP_TOOLTIP = {
    "html": (
        "<div style='background-color:#2c3e50;color:#ffffff;padding:10px 12px;"
        "border-radius:6px;max-width:340px;font-family:sans-serif;"
        "box-shadow:0 2px 10px rgba(0,0,0,0.45);'>"
        "{tooltip_text}</div>"
    ),
    "style": {
        "color": "white",
        "backgroundColor": "#2c3e50",
        "fontSize": "13px",
    },
}

MULTI_DAY_POINT_COLOR = [153, 50, 204, 235]


def render_trip_map(plan: dict):
    path_rows = []
    # Одна точка на карте на координаты; при повторе в разные дни — общая подсказка
    locations = defaultdict(lambda: {
        "lat": 0.0,
        "lon": 0.0,
        "visits": [],
        "day_color": None,
    })

    for day_block in plan["schedule"]:
        color = TRIP_DAY_COLORS[(day_block["day"] - 1) % len(TRIP_DAY_COLORS)]
        path = [[stop["lon"], stop["lat"]] for stop in day_block["stops"]]
        if len(path) >= 2:
            path_rows.append({
                "path": path,
                "day": day_block["day"],
                "color": color,
            })
        for stop in day_block["stops"]:
            key = (round(float(stop["lat"]), 5), round(float(stop["lon"]), 5))
            loc = locations[key]
            loc["lat"] = float(stop["lat"])
            loc["lon"] = float(stop["lon"])
            loc["visits"].append({
                "day": day_block["day"],
                "order": stop["order"],
                "name": stop["name"],
                "type": stop["type"],
            })
            if loc["day_color"] is None:
                loc["day_color"] = color

    point_rows = []
    for loc in locations.values():
        if len(loc["visits"]) > 1:
            point_color = MULTI_DAY_POINT_COLOR
        else:
            point_color = loc["day_color"]

        point_rows.append({
            "lon": loc["lon"],
            "lat": loc["lat"],
            "color": point_color,
            "tooltip_text": _build_trip_tooltip(loc["visits"]),
        })

    if not point_rows:
        return

    layers = []
    if path_rows:
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=path_rows,
                get_path="path",
                get_color="color",
                get_width=4,
                width_min_pixels=2,
                pickable=False,
            )
        )

    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            data=point_rows,
            get_position=["lon", "lat"],
            get_color="color",
            get_radius=80,
            radius_min_pixels=7,
            pickable=True,
            auto_highlight=True,
        )
    )

    center = point_rows[0]
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=center["lat"],
            longitude=center["lon"],
            zoom=11,
            pitch=40,
        ),
        map_style=None,
        tooltip=TRIP_MAP_TOOLTIP,
    )
    st.pydeck_chart(deck)
    if any(len(loc["visits"]) > 1 for loc in locations.values()):
        st.caption("🟣 Фиолетовые точки — место включено в маршрут более чем на один день.")


def fetch_discover(city: str, obj_type: str, n: int, seed: Optional[int] = None) -> Optional[list]:
    params = {
        "top_n": n,
        "filter_city": city,
        "filter_type": obj_type,
    }
    if seed is not None:
        params["seed"] = seed

    try:
        response = requests.get(f"{API_URL}/discover", params=params, timeout=30)
        if response.status_code == 200:
            return response.json().get("recommendations", [])
    except Exception:
        pass
    return None


def render_recommendations(records: list, allow_favorites: bool = False):
    for row in records:
        name = row["name"]
        if allow_favorites:
            api_log_view(name)

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"### 🏛️ {row['name']}")
                current_loc = row.get('locality', '')
                if pd.isna(current_loc) or str(current_loc).strip() == '':
                    current_loc = row.get('region', 'Россия')

                st.markdown(f"**Категория:** `{row['type']}` | 📍 `{current_loc}`")

            with col2:
                st.link_button("Открыть на карте 🔗", row['Ресурс'], use_container_width=True)
                if allow_favorites:
                    in_fav = name in st.session_state.favorites
                    fav_label = "★ Убрать из избранного" if in_fav else "☆ В избранное"
                    if st.button(fav_label, key=f"fav_{hash(name)}", use_container_width=True):
                        if api_toggle_favorite(name, in_fav):
                            st.session_state.personal_version += 1
                            st.session_state.discover_key = None
                            st.session_state.recs = None
                            st.session_state.recs_source = None
                            st.rerun()
                        st.error("Не удалось обновить избранное")

            st.write(row['Описание'])


# Интерфейс
names = get_object_names()

if not names:
    st.error("Не удалось подключиться к API. Убедись, что uvicorn запущен!")
else:
    # Основной выбор объекта
    selected_object = st.selectbox("Выберите достопримечательность:", names)
    start_search = st.button("Сформировать персональный маршрут", use_container_width=True)

    # === ИНИЦИАЛИЗАЦИЯ ХРАНИЛИЩА СОСТОЯНИЙ ===
    if "recs" not in st.session_state:
        st.session_state.recs = None
    if "search_city" not in st.session_state:
        st.session_state.search_city = None
    if "search_type" not in st.session_state:
        st.session_state.search_type = None
    if "search_object" not in st.session_state:
        st.session_state.search_object = None
    if "search_dist_weight" not in st.session_state:
        st.session_state.search_dist_weight = None
    if "search_top_n" not in st.session_state:
        st.session_state.search_top_n = None
    if "search_hotel_radius" not in st.session_state:
        st.session_state.search_hotel_radius = hotel_radius
    if "hotels" not in st.session_state:
        st.session_state.hotels = None
    if "hotels_page" not in st.session_state:
        st.session_state.hotels_page = 1
    if "recs_source" not in st.session_state:
        st.session_state.recs_source = None
    if "discover_key" not in st.session_state:
        st.session_state.discover_key = None
    if "trip_plan" not in st.session_state:
        st.session_state.trip_plan = None

    discover_key = (
        selected_city,
        selected_type,
        top_n,
        st.session_state.get("personal_version", 0),
        st.session_state.get("user_id"),
    )
    refresh_discover = st.session_state.pop("refresh_discover_pending", False)

    need_auto_recs = (
        st.session_state.recs_source != "anchor"
        and (
            st.session_state.recs is None
            or st.session_state.discover_key != discover_key
            or refresh_discover
        )
    )

    if need_auto_recs and not start_search:
        if is_logged_in:
            with st.spinner("Подбираем рекомендации для вас..."):
                raw_personal = fetch_personal(
                    selected_city, selected_type, top_n, dist_weight
                )
                if raw_personal:
                    with st.spinner("Подгружаем информацию и гео-ссылки..."):
                        st.session_state.recs = enrich_recommendations(raw_personal)
                        st.session_state.recs_source = "personal"
                        st.session_state.discover_key = discover_key
                        st.session_state.hotels = None
                elif st.session_state.recs is None:
                    st.warning("⚠️ Не удалось загрузить персональные рекомендации.")
        else:
            with st.spinner("Подбираем разнообразные места..."):
                raw_discover = fetch_discover(selected_city, selected_type, top_n)
                if raw_discover:
                    with st.spinner("Подгружаем информацию и гео-ссылки..."):
                        st.session_state.recs = enrich_recommendations(raw_discover)
                        st.session_state.recs_source = "discover"
                        st.session_state.discover_key = discover_key
                        st.session_state.hotels = None
                elif st.session_state.recs is None:
                    st.warning("⚠️ По выбранным фильтрам не найдено объектов для подборки.")

    if start_search:
        with st.spinner('Алгоритм рассчитывает сходство...'):
            st.session_state.search_city = selected_city
            st.session_state.search_type = selected_type
            st.session_state.search_object = selected_object
            st.session_state.search_dist_weight = dist_weight
            st.session_state.search_top_n = top_n

            params = {
                "top_n": top_n,
                "distance_weight": dist_weight,
                "filter_city": selected_city,
                "filter_type": selected_type
            }

            encoded_object = urllib.parse.quote(selected_object)
            response = requests.get(f"{API_URL}/recommend/{encoded_object}", params=params)

            if response.status_code == 200:
                raw_recs = response.json()["recommendations"]

                if not raw_recs:
                    st.warning("⚠️ По вашему запросу не найдено похожих объектов.")
                    st.session_state.recs = None
                    st.session_state.recs_source = None
                else:
                    with st.spinner('Подгружаем информацию и гео-ссылки...'):
                        st.session_state.recs = enrich_recommendations(raw_recs)
                        st.session_state.recs_source = "anchor"
                        st.session_state.discover_key = None
                        st.session_state.hotels = None
            else:
                st.error(f"Ошибка при получении данных (Код: {response.status_code})")

    anchor_params_changed = (
        st.session_state.recs_source == "anchor"
        and st.session_state.recs is not None
        and (
            st.session_state.search_city != selected_city
            or st.session_state.search_type != selected_type
            or st.session_state.search_object != selected_object
            or st.session_state.search_dist_weight != dist_weight
            or st.session_state.search_top_n != top_n
        )
    )

    if anchor_params_changed:
        st.info(
            "🔄 Фильтры или якорь изменились. Нажмите «Сформировать персональный маршрут», "
            "чтобы обновить результаты."
        )

    if st.session_state.recs:
        if st.session_state.recs_source == "anchor":
            st.subheader("📍 Персональный маршрут")
        elif st.session_state.recs_source == "personal":
            col_title, col_btn = st.columns([4, 1])
            with col_title:
                st.subheader("✨ Рекомендации для вас")
                if st.session_state.favorites:
                    st.caption("На основе избранного и просмотренных мест.")
                else:
                    st.caption(
                        "Добавляйте места в избранное — подборка станет точнее. "
                        "Пока показаны случайные идеи."
                    )
            with col_btn:
                if st.button("🔄 Обновить", key="refresh_personal", use_container_width=True):
                    st.session_state.refresh_discover_pending = True
                    st.session_state.discover_key = None
                    st.rerun()
        else:
            col_title, col_btn = st.columns([4, 1])
            with col_title:
                st.subheader("🎲 Подборка для вдохновения")
                st.caption("Случайные места с разными типами и городами.")
            with col_btn:
                if st.button("🎲 Другая подборка", key="refresh_discover", use_container_width=True):
                    st.session_state.refresh_discover_pending = True
                    st.session_state.discover_key = None
                    st.rerun()

        render_recommendations(
            st.session_state.recs,
            allow_favorites=is_logged_in,
        )

    # --- ПЛАНИРОВЩИК ПОЕЗДКИ ПО ДНЯМ ---
    st.divider()
    st.subheader("📅 План поездки по дням")
    st.caption(
        "Система подберёт достопримечательности в выбранном городе, распределит их по дням "
        "и выстроит порядок посещения с учётом расстояний."
    )

    if selected_city == "Все города":
        st.info("Для планирования маршрута выберите конкретный город в фильтре выше.")
    else:
        trip_col1, trip_col2, trip_col3, trip_col4 = st.columns([1, 1, 1, 1])
        with trip_col1:
            trip_days = st.number_input("Количество дней", min_value=1, max_value=7, value=2)
        with trip_col2:
            trip_points = st.number_input("Точек в день", min_value=2, max_value=8, value=4)
        with trip_col3:
            trip_radius = st.slider(
                "Радиус города (км)",
                min_value=10,
                max_value=60,
                value=30,
                help="Точки дальше от центра города не попадут в маршрут (отсекает ошибки в данных).",
            )
        with trip_col4:
            st.write("")
            build_trip = st.button(
                "📅 Сформировать маршрут",
                use_container_width=True,
                key="build_trip_plan",
            )

        if build_trip:
            with st.spinner(f"Строим маршрут по {selected_city}..."):
                plan = fetch_trip_plan(
                    selected_city,
                    int(trip_days),
                    int(trip_points),
                    selected_type,
                    float(trip_radius),
                )
                if plan:
                    st.session_state.trip_plan = plan

    if st.session_state.trip_plan:
        if st.session_state.trip_plan.get("city") != selected_city:
            st.warning("Город в фильтре изменился — сформируйте маршрут заново.")
        else:
            render_trip_plan(st.session_state.trip_plan)
            st.markdown("**Карта маршрута** (цвет линии — номер дня)")
            render_trip_map(st.session_state.trip_plan)

    # --- БЛОК ПОИСКА ОТЕЛЕЙ ---
    if st.session_state.recs:
        st.divider()
        st.subheader("🏨 Поиск жилья поблизости")

        # Выбор объекта из списка рекомендаций
        rec_names = [r['name'] for r in st.session_state.recs]
        selected_rec_name = st.selectbox("Выберите достопримечательность, чтобы найти отели рядом:", rec_names)
        selected_rec = next(r for r in st.session_state.recs if r['name'] == selected_rec_name)

        # Кнопка поиска отелей
        if st.button(f"Найти отели в радиусе {hotel_radius} км"):
            st.session_state.search_hotel_radius = hotel_radius

            with st.spinner(f'Ищем отели вокруг {selected_rec_name}...'):
                params = {
                    "lat": selected_rec['lat'],
                    "lon": selected_rec['lon'],
                    "radius": float(hotel_radius)
                }
                h_response = requests.get(f"{API_URL}/hotels/near", params=params)

                if h_response.status_code == 200:
                    st.session_state.hotels = h_response.json().get("hotels", [])
                    st.session_state.hotels_page = 1
                else:
                    st.error("Ошибка API при поиске отелей.")

        if st.session_state.search_hotel_radius != hotel_radius:
            st.warning("📏 Радиус изменен в меню. Нажмите кнопку ниже, чтобы обновить карту отелей.")

        if st.session_state.hotels is not None:
            hotels = st.session_state.hotels

            if not hotels:
                st.warning(
                    f"В радиусе {hotel_radius} км отелей не найдено. Попробуйте увеличить радиус в боковом меню.")
            else:
                st.success(f"Найдено объектов: {len(hotels)}")

                df_hotels = pd.DataFrame(hotels)
                df_to_show = df_hotels[['name', 'address', 'distance_km', 'website']].copy()
                df_to_show.columns = ['Название', 'Адрес', 'Расстояние (км)', 'Сайт']

                total_pages = max(1, (len(df_to_show) + HOTELS_PER_PAGE - 1) // HOTELS_PER_PAGE)
                if st.session_state.hotels_page > total_pages:
                    st.session_state.hotels_page = total_pages

                page = st.session_state.hotels_page
                start_idx = (page - 1) * HOTELS_PER_PAGE
                end_idx = start_idx + HOTELS_PER_PAGE
                page_df = df_to_show.iloc[start_idx:end_idx].reset_index(drop=True)

                st.dataframe(page_df, hide_index=True, use_container_width=True)

                col_prev, col_info, col_next = st.columns([1, 2, 1])
                with col_prev:
                    if st.button("← Назад", disabled=page <= 1, key="hotels_prev"):
                        st.session_state.hotels_page -= 1
                        st.rerun()
                with col_info:
                    st.caption(f"Страница {page} из {total_pages}")
                with col_next:
                    if st.button("Вперёд →", disabled=page >= total_pages, key="hotels_next"):
                        st.session_state.hotels_page += 1
                        st.rerun()

                df_attractions = pd.DataFrame(st.session_state.recs)
                df_grouped = df_attractions.groupby(['lat', 'lon']).agg({
                    'name': lambda x: '<br/>• '.join(x),
                    'type': 'first',
                    'region': 'first'
                }).reset_index()

                df_grouped['tooltip_text'] = '🏛️ <b>Достопримечательности:</b><br/>• ' + df_grouped['name']

                df_hotels_map = pd.DataFrame(hotels)
                df_hotels_map['tooltip_text'] = (
                    '🏨 <b>' + df_hotels_map['name'] + '</b><br/>📍 ' + df_hotels_map['address']
                    + '<br/>📏 ' + df_hotels_map['distance_km'].round(1).astype(str) + ' км'
                )

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

                dynamic_zoom = 14 - (hotel_radius / 10)
                view_state = pdk.ViewState(
                    latitude=selected_rec['lat'],
                    longitude=selected_rec['lon'],
                    zoom=max(dynamic_zoom, 10),
                    pitch=45,
                )

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