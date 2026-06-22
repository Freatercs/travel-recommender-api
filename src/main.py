# src/main.py
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from src.api.routes import auth, interactions, recommendations, trip
from src.db.database import init_db
from src.ml.preprocess import DataLoader
from src.ml.model import RecommenderEngine

# Глобальное хранилище данных
data_store = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Этот блок выполняется ОДИН РАЗ при старте сервера.
    Здесь мы загружаем все тяжелые данные в память.
    """
    # 1. Пути к файлам
    attractions_path = "data/raw/russian_tourist_attraction_ru.csv"
    hotels_path = "data/raw/russian-hotels.xlsx"

    try:
        init_db()
        print("✅ База данных инициализирована.")

        # 2. Инициализируем загрузчик
        loader = DataLoader(attractions_path, hotels_path)

        # 3. Загружаем достопримечательности и создаем модель
        df_attractions = loader.load_attractions()
        engine = RecommenderEngine(df_attractions)
        engine.build_model()

        # 4. Загружаем отели
        df_hotels = loader.load_hotels()

        # 5. Сохраняем всё в глобальный store
        data_store["engine"] = engine
        data_store["df"] = df_attractions
        data_store["hotels_df"] = df_hotels

        print("✅ Система готова: Достопримечательности и Отели загружены.")

    except Exception as e:
        print(f"❌ Ошибка при старте сервера: {e}")

    yield
    # Очистка при выключении
    data_store.clear()


# Создаем приложение и подключаем lifespan
app = FastAPI(lifespan=lifespan, title="Travel Recommender API")
app.state.data_store = data_store

app.include_router(auth.router)
app.include_router(interactions.router)
app.include_router(recommendations.router)
app.include_router(trip.router)


@app.get("/recommend/{item_name}")
def get_recommendations(
    item_name: str,
    top_n: int = 5,
    distance_weight: float = 0.3,
    filter_city: str = "Все города",  # Принимаем город из query-параметров
    filter_type: str = "Все типы"     # Принимаем тип из query-параметров
):
    engine = data_store.get("engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Model not initialized")

    # Передаем фильтры в метод нашей гибридной модели
    recs = engine.recommend(
        item_name,
        top_n=top_n,
        distance_weight=distance_weight,
        filter_city=filter_city,
        filter_type=filter_type
    )

    # Убрал жесткий вылет по 404, если объекты просто отфильтровались.
    return {"source": item_name, "recommendations": recs}


@app.get("/discover")
def discover_attractions(
    top_n: int = 5,
    filter_city: str = "Все города",
    filter_type: str = "Все типы",
    seed: Optional[int] = None,
):
    engine = data_store.get("engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Model not initialized")

    items = engine.discover_diverse(
        top_n=top_n,
        filter_city=filter_city,
        filter_type=filter_type,
        seed=seed,
    )
    return {"mode": "discover", "recommendations": items}


@app.get("/hotels/near")
def get_nearby_hotels(lat: float, lon: float, radius: float = 5.0):
    engine = data_store.get("engine")
    hotels_df = data_store.get("hotels_df")

    if hotels_df is None:
        raise HTTPException(status_code=503, detail="Hotels database not loaded")

    nearby = engine.find_nearby_hotels(hotels_df, lat, lon, radius_km=radius)
    return {"hotels": nearby}


@app.get("/debug/names")
def get_names():
    df = data_store.get("df")
    if df is None:
        return {"error": "Data not loaded"}
    return {"sample_names": df['name'].tolist()}