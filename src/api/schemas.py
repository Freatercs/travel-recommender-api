from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class InteractionCreate(BaseModel):
    attraction_name: str = Field(min_length=1, max_length=512)
    event_type: Literal["view", "favorite"]


class InteractionOut(BaseModel):
    id: int
    attraction_name: str
    event_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class FavoritesOut(BaseModel):
    favorites: List[str]


class PersonalRecommendParams(BaseModel):
    top_n: int = 5
    distance_weight: float = 0.3
    filter_city: str = "Все города"
    filter_type: str = "Все типы"
