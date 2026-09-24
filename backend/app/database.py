from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей (таблиц)."""


def get_db():
    """Открывает сессию БД на время одного запроса и закрывает её после."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
