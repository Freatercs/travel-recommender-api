from collections import Counter
from typing import List, Set, Tuple

from sqlalchemy.orm import Session

from src.db.models import User, UserInteraction


def get_user_anchors(db: Session, user_id: int, limit: int = 8) -> List[str]:
    """
    Якоря для персональных рекомендаций: избранное важнее просмотров.
    """
    favorites = (
        db.query(UserInteraction.attraction_name)
        .filter(UserInteraction.user_id == user_id, UserInteraction.event_type == "favorite")
        .order_by(UserInteraction.created_at.desc())
        .all()
    )
    views = (
        db.query(UserInteraction.attraction_name)
        .filter(UserInteraction.user_id == user_id, UserInteraction.event_type == "view")
        .order_by(UserInteraction.created_at.desc())
        .limit(50)
        .all()
    )

    weighted: List[Tuple[str, int]] = []
    for (name,) in favorites:
        weighted.append((name, 3))
    for (name,) in views:
        weighted.append((name, 1))

    scores = Counter()
    order = []
    for name, w in weighted:
        scores[name] += w
        if name not in order:
            order.append(name)

    ranked = sorted(order, key=lambda n: scores[n], reverse=True)
    return ranked[:limit]


def get_user_favorite_names(db: Session, user_id: int) -> Set[str]:
    rows = (
        db.query(UserInteraction.attraction_name)
        .filter(UserInteraction.user_id == user_id, UserInteraction.event_type == "favorite")
        .all()
    )
    return {r[0] for r in rows}


def get_user_interacted_names(db: Session, user_id: int) -> Set[str]:
    rows = (
        db.query(UserInteraction.attraction_name)
        .filter(UserInteraction.user_id == user_id)
        .all()
    )
    return {r[0] for r in rows}
