from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Cinema
from app.schemas import CinemaIn, CinemaOut

router = APIRouter(prefix="/api/cinemas", tags=["Кинотеатры"])


def get_cinema_or_404(db: Session, cinema_id: int) -> Cinema:
    cinema = db.get(Cinema, cinema_id)
    if cinema is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Кинотеатр не найден")
    return cinema


@router.get("", response_model=list[CinemaOut], dependencies=[Depends(get_current_user)])
def list_cinemas(db: Session = Depends(get_db)):
    return db.scalars(select(Cinema).order_by(Cinema.name)).all()


@router.get("/{cinema_id}", response_model=CinemaOut, dependencies=[Depends(get_current_user)])
def get_cinema(cinema_id: int, db: Session = Depends(get_db)):
    return get_cinema_or_404(db, cinema_id)


@router.post("", response_model=CinemaOut, status_code=201, dependencies=[Depends(require_admin)])
def create_cinema(data: CinemaIn, db: Session = Depends(get_db)):
    cinema = Cinema(**data.model_dump())
    db.add(cinema)
    db.commit()
    db.refresh(cinema)
    return cinema


@router.put("/{cinema_id}", response_model=CinemaOut, dependencies=[Depends(require_admin)])
def update_cinema(cinema_id: int, data: CinemaIn, db: Session = Depends(get_db)):
    cinema = get_cinema_or_404(db, cinema_id)
    for field, value in data.model_dump().items():
        setattr(cinema, field, value)
    db.commit()
    db.refresh(cinema)
    return cinema


@router.delete("/{cinema_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_cinema(cinema_id: int, db: Session = Depends(get_db)):
    db.delete(get_cinema_or_404(db, cinema_id))
    db.commit()
