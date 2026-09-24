"""Запросы справочной службы из задания."""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Cinema, Film, Screening
from app.schemas import CinemaOut, FilmOut, ScreeningOut

router = APIRouter(
    prefix="/api/queries", tags=["Запросы"], dependencies=[Depends(get_current_user)]
)


def is_upcoming():
    """Условие «сеанс ещё не прошёл»: сегодня или позже."""
    return Screening.date >= dt.date.today()


@router.get("/repertoire/{cinema_id}", response_model=list[ScreeningOut])
def cinema_repertoire(cinema_id: int, db: Session = Depends(get_db)):
    """Репертуар кинотеатра."""
    if db.get(Cinema, cinema_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Кинотеатр не найден")
    stmt = (
        select(Screening)
        .where(Screening.cinema_id == cinema_id, is_upcoming())
        .order_by(Screening.date, Screening.time, Screening.hall)
    )
    return db.scalars(stmt).all()


@router.get("/cinemas-by-genre", response_model=list[CinemaOut])
def cinemas_by_genre(genre: str, db: Session = Depends(get_db)):
    """В каких кинотеатрах можно посмотреть фильмы жанра (боевики, комедии...)."""
    stmt = (
        select(Cinema)
        .join(Cinema.screenings)
        .join(Screening.film)
        .where(func.lower(Film.genre) == genre.lower(), is_upcoming())
        .distinct()
        .order_by(Cinema.name)
    )
    return db.scalars(stmt).all()


@router.get("/session", response_model=list[ScreeningOut])
def session_info(cinema_id: int, date: dt.date, time: dt.time, db: Session = Depends(get_db)):
    """Сеанс в заданном кинотеатре: отсюда берутся число свободных мест и цена.

    Список, потому что в одно время в разных залах могут идти разные фильмы.
    """
    stmt = (
        select(Screening)
        .where(
            Screening.cinema_id == cinema_id,
            Screening.date == date,
            Screening.time == time,
        )
        .order_by(Screening.hall)
    )
    return db.scalars(stmt).all()


@router.get("/films-by-director", response_model=list[FilmOut])
def films_by_director(director: str, db: Session = Depends(get_db)):
    """Какие фильмы заданного режиссёра сейчас демонстрируются в кинотеатрах."""
    stmt = (
        select(Film)
        .join(Film.screenings)
        .where(Film.director.ilike(f"%{director}%"), is_upcoming())
        .distinct()
        .order_by(Film.title)
    )
    return db.scalars(stmt).all()
