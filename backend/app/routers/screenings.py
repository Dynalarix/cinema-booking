from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Cinema, Film, Screening
from app.schemas import ScreeningIn, ScreeningOut, SellTickets

router = APIRouter(prefix="/api/screenings", tags=["Репертуар"])


def get_screening_or_404(db: Session, screening_id: int) -> Screening:
    screening = db.get(Screening, screening_id)
    if screening is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сеанс не найден")
    return screening


def validate(db: Session, data: ScreeningIn) -> None:
    """Проверки, которые нельзя описать в схеме: связь с кинотеатром и фильмом."""
    cinema = db.get(Cinema, data.cinema_id)
    if cinema is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Кинотеатр не найден")
    if db.get(Film, data.film_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Фильм не найден")
    if data.hall > cinema.halls_count:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"В кинотеатре «{cinema.name}» всего залов: {cinema.halls_count}",
        )
    if data.free_seats > cinema.seats_count:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Свободных мест не может быть больше, чем мест в кинотеатре ({cinema.seats_count})",
        )


def save(db: Session, screening: Screening) -> Screening:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "В этом зале на это время уже есть сеанс"
        )
    db.refresh(screening)
    return screening


@router.get("", response_model=list[ScreeningOut], dependencies=[Depends(get_current_user)])
def list_screenings(db: Session = Depends(get_db)):
    stmt = select(Screening).order_by(Screening.date, Screening.time, Screening.hall)
    return db.scalars(stmt).all()


@router.get("/{screening_id}", response_model=ScreeningOut, dependencies=[Depends(get_current_user)])
def get_screening(screening_id: int, db: Session = Depends(get_db)):
    return get_screening_or_404(db, screening_id)


@router.post("", response_model=ScreeningOut, status_code=201, dependencies=[Depends(require_admin)])
def create_screening(data: ScreeningIn, db: Session = Depends(get_db)):
    validate(db, data)
    screening = Screening(**data.model_dump())
    db.add(screening)
    return save(db, screening)


@router.put("/{screening_id}", response_model=ScreeningOut, dependencies=[Depends(require_admin)])
def update_screening(screening_id: int, data: ScreeningIn, db: Session = Depends(get_db)):
    screening = get_screening_or_404(db, screening_id)
    validate(db, data)
    for field, value in data.model_dump().items():
        setattr(screening, field, value)
    return save(db, screening)


@router.delete("/{screening_id}", status_code=204, dependencies=[Depends(require_admin)])
def delete_screening(screening_id: int, db: Session = Depends(get_db)):
    db.delete(get_screening_or_404(db, screening_id))
    db.commit()


@router.post("/{screening_id}/sell", response_model=ScreeningOut, dependencies=[Depends(get_current_user)])
def sell_tickets(screening_id: int, data: SellTickets, db: Session = Depends(get_db)):
    """Продажа билетов: уменьшает число свободных мест.

    Проверка и уменьшение делаются одним UPDATE, поэтому два сотрудника,
    продающие билеты одновременно, не смогут продать больше, чем есть мест.
    """
    result = db.execute(
        update(Screening)
        .where(Screening.id == screening_id, Screening.free_seats >= data.count)
        .values(free_seats=Screening.free_seats - data.count)
    )
    db.commit()
    screening = get_screening_or_404(db, screening_id)
    if result.rowcount == 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Недостаточно свободных мест (осталось {screening.free_seats})",
        )
    return screening
