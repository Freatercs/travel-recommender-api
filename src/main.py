from fastapi import FastAPI, HTTPException
from src.ml.preprocess import DataLoader
from src.ml.model import RecommenderEngine

app = FastAPI(title="Travel Recommender API")
data_store = {}


@app.on_event("startup")
async def startup_event():
    # Загрузка данных
    loader = DataLoader("data/raw/russian_tourist_attractions.csv")
    df = loader.load_data()

    # Инициализация и "обучение" модели
    engine = RecommenderEngine(df)
    engine.build_model()

    data_store["df"] = df
    data_store["engine"] = engine


@app.get("/recommend/{item_name}")
def get_recommendations(item_name: str, top_n: int = 5, distance_weight: float = 0.3):
    engine = data_store.get("engine")
    # Передаем параметры в метод нашей модели
    recs = engine.recommend(item_name, top_n=top_n, distance_weight=distance_weight)

    if not recs:
        raise HTTPException(status_code=404, detail="Object not found")

    return {"source": item_name, "recommendations": recs}

@app.get("/debug/names")
def get_names():
    # Возвращает первые 20 названий из базы, чтобы ты мог их скопировать
    return {"sample_names": data_store["df"]['name'].head(20).tolist()}