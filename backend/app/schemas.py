"""Схемы Pydantic: описывают, какие данные API принимает и возвращает."""

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class CinemaIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=50)
    seats_count: int = Field(gt=0)
    halls_count: int = Field(gt=0)
    status: str = Field(min_length=1, max_length=50)


class CinemaOut(CinemaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class FilmIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    director: str = Field(min_length=1, max_length=200)
    operator: str = Field(min_length=1, max_length=200)
    actors: str = Field(min_length=1)
    genre: str = Field(min_length=1, max_length=50)
    studio: str = Field(min_length=1, max_length=200)


class FilmOut(FilmIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ScreeningIn(BaseModel):
    cinema_id: int
    film_id: int
    hall: int = Field(gt=0)
    date: dt.date
    time: dt.time
    price: int = Field(ge=0)
    free_seats: int = Field(ge=0)


class ScreeningOut(ScreeningIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cinema_name: str
    film_title: str


class SellTickets(BaseModel):
    count: int = Field(gt=0)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    role: str
