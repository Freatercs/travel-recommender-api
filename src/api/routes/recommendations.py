from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.api.services import get_user_anchors, get_user_interacted_names
from src.db.database import get_db
from src.db.models import User

router = APIRouter(prefix="/recommend", tags=["recommend"])


def _get_engine(request):
    store = getattr(request.app.state, "data_store", None) or {}
    engine = store.get("engine")
    if not engine:
        raise HTTPException(status_code=503, detail="Model not initialized")
    return engine


@router.get("/personal")
def personal_recommendations(
    request: Request,
    top_n: int = 5,
    distance_weight: float = 0.3,
    filter_city: str = "Все города",
    filter_type: str = "Все типы",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    engine = _get_engine(request)
    anchors = get_user_anchors(db, current_user.id)
    exclude = get_user_interacted_names(db, current_user.id)

    items = engine.recommend_personalized(
        anchor_names=anchors,
        top_n=top_n,
        distance_weight=distance_weight,
        filter_city=filter_city,
        filter_type=filter_type,
        exclude_names=exclude,
    )

    mode = "personal" if anchors else "discover_fallback"
    return {
        "mode": mode,
        "anchors_used": anchors,
        "recommendations": items,
    }
