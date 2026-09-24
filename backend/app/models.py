import datetime as dt

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Cinema(Base):
    """Кинотеатр."""

    __tablename__ = "cinemas"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(50))
    seats_count: Mapped[int]
    halls_count: Mapped[int]
    status: Mapped[str] = mapped_column(String(50))

    screenings: Mapped[list["Screening"]] = relationship(
        back_populates="cinema", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("seats_count > 0"),
        CheckConstraint("halls_count > 0"),
    )


class Film(Base):
    """Фильм."""

    __tablename__ = "films"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    director: Mapped[str] = mapped_column(String(200))
    operator: Mapped[str] = mapped_column(String(200))
    actors: Mapped[str] = mapped_column(Text)
    genre: Mapped[str] = mapped_column(String(50))
    studio: Mapped[str] = mapped_column(String(200))

    screenings: Mapped[list["Screening"]] = relationship(
        back_populates="film", cascade="all, delete-orphan", passive_deletes=True
    )


class Screening(Base):
    """Сеанс (запись репертуара): какой фильм, где, в каком зале и когда идёт."""

    __tablename__ = "screenings"

    id: Mapped[int] = mapped_column(primary_key=True)
    cinema_id: Mapped[int] = mapped_column(ForeignKey("cinemas.id", ondelete="CASCADE"))
    film_id: Mapped[int] = mapped_column(ForeignKey("films.id", ondelete="CASCADE"))
    hall: Mapped[int]
    date: Mapped[dt.date]
    time: Mapped[dt.time]
    price: Mapped[int]
    free_seats: Mapped[int]

    # lazy="joined" — кинотеатр и фильм подгружаются одним запросом вместе с сеансом
    cinema: Mapped[Cinema] = relationship(back_populates="screenings", lazy="joined")
    film: Mapped[Film] = relationship(back_populates="screenings", lazy="joined")

    __table_args__ = (
        # В одном зале в одно и то же время может идти только один сеанс
        UniqueConstraint("cinema_id", "hall", "date", "time"),
        CheckConstraint("hall > 0"),
        CheckConstraint("price >= 0"),
        CheckConstraint("free_seats >= 0"),
    )

    @property
    def cinema_name(self) -> str:
        return self.cinema.name

    @property
    def film_title(self) -> str:
        return self.film.title


class User(Base):
    """Работник справочной службы. role: 'admin' или 'staff'."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20))
