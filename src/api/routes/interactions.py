from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.deps import get_current_user
from src.api.schemas import FavoritesOut, InteractionCreate, InteractionOut
from src.db.database import get_db
from src.db.models import User, UserInteraction

router = APIRouter(prefix="/interactions", tags=["interactions"])


@router.post("", response_model=InteractionOut)
def add_interaction(
    payload: InteractionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = payload.attraction_name.strip()
    event_type = payload.event_type

    existing = (
        db.query(UserInteraction)
        .filter(
            UserInteraction.user_id == current_user.id,
            UserInteraction.attraction_name == name,
            UserInteraction.event_type == event_type,
        )
        .first()
    )
    if existing:
        return existing

    row = UserInteraction(
        user_id=current_user.id,
        attraction_name=name,
        event_type=event_type,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/favorite/{attraction_name}")
def remove_favorite(
    attraction_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = (
        db.query(UserInteraction)
        .filter(
            UserInteraction.user_id == current_user.id,
            UserInteraction.attraction_name == attraction_name,
            UserInteraction.event_type == "favorite",
        )
        .delete()
    )
    db.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Объект не найден в избранном")
    return {"ok": True}


@router.get("/favorites", response_model=FavoritesOut)
def list_favorites(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(UserInteraction.attraction_name)
        .filter(
            UserInteraction.user_id == current_user.id,
            UserInteraction.event_type == "favorite",
        )
        .order_by(UserInteraction.created_at.desc())
        .all()
    )
    return FavoritesOut(favorites=[r[0] for r in rows])
