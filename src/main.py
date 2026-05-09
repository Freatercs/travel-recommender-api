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
def get_recommendations(item_name: str):
    engine = data_store.get("engine")
    recs = engine.recommend(item_name)
    if not recs:
        raise HTTPException(status_code=404, detail="Object not found or no recommendations")
    return {"source": item_name, "recommendations": recs}