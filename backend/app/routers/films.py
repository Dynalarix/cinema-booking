from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Film
from app.schemas import FilmIn, FilmOut

router = APIRouter(prefix="/api/films", tags=["Фильмы"])


def get_film_or_404(db: Session, film_id: int) -> Film:
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Фильм не найден")
    return film


@router.get("", response_model=list[FilmOut], dependencies=[Depends(get_current_user)])
def list_films(db: Session = Depends(get_db)):
    return db.scalars(select(Film).order_by(Film.title)).all()


@router.get("/{film_id}", response_model=FilmOut, dependencies=[Depends(get_current_user)])
def get_film(film_id: int, db: Session = Depends(get_db)):
    return get_film_or_404(db, film_id)


@router.post("", response_model=FilmOut, status_code=201, dependencies=[Depends(require_admin)])
def create_film(data: FilmIn, db: Session = Depends(get_db)):
    film = Film(**data.model_dump())
    db.add(film)
    db.commit()
    db.refresh(film)
    return film


@router.put("/{film_id}", response_model=FilmOut, dependencies=[Depends(require_admin)])
def update_film(film_id: int, data: FilmIn, db: Session = Depends(get_db)):
    film = get_film_or_404(db, film_id)
    for field, value in data.model_dump().items():
        setattr(film, field, value)
    db.commit()
    db.refresh(film)
    return film


@router.delete("/{film_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_film(film_id: int, db: Session = Depends(get_db)):
    # Сеансы этого фильма удаляются вместе с ним (ON DELETE CASCADE)
    db.delete(get_film_or_404(db, film_id))
    db.commit()
