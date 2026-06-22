from typing import Optional

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/trip", tags=["trip"])


def _get_engine(request: Request):
    store = getattr(request.app.state, "data_store", None) or {}
    engine = store.get("engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Model not initialized")
    return engine


@router.get("/plan")
def plan_trip(
    request: Request,
    city: str,
    days: int = 1,
    points_per_day: int = 4,
    filter_type: str = "Все типы",
    seed: Optional[int] = None,
    city_radius_km: float = 30.0,
):
    engine = _get_engine(request)
    result = engine.plan_trip(
        city=city,
        days=days,
        points_per_day=points_per_day,
        filter_type=filter_type,
        seed=seed,
        city_radius_km=city_radius_km,
    )

    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    return result
