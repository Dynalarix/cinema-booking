"""Начальные данные: пользователи и примеры кинотеатров, фильмов и сеансов."""

import datetime as dt
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.models import Cinema, Film, Screening, User

CINEMAS = [
    ("Рассвет", "ул. Ленина, 12", "Высшая", 600, 3, "Работает"),
    ("Звезда", "пр. Мира, 45", "Первая", 350, 2, "Работает"),
    ("Спутник", "ул. Гагарина, 7", "Вторая", 200, 1, "Работает"),
    ("Юность", "ул. Садовая, 3", "Вторая", 250, 1, "На ремонте"),
]

FILMS = [
    ("Брат", "Алексей Балабанов", "Сергей Астахов",
     "Сергей Бодров-мл., Виктор Сухоруков, Светлана Письмиченко", "Боевик", "СТВ"),
    ("Брат 2", "Алексей Балабанов", "Сергей Астахов",
     "Сергей Бодров-мл., Виктор Сухоруков, Ирина Салтыкова", "Боевик", "СТВ"),
    ("Белое солнце пустыни", "Владимир Мотыль", "Эдуард Розовский",
     "Анатолий Кузнецов, Спартак Мишулин, Павел Луспекаев", "Боевик", "Мосфильм"),
    ("Бриллиантовая рука", "Леонид Гайдай", "Игорь Черных",
     "Юрий Никулин, Андрей Миронов, Анатолий Папанов", "Комедия", "Мосфильм"),
    ("Иван Васильевич меняет профессию", "Леонид Гайдай", "Сергей Полуянов",
     "Юрий Яковлев, Леонид Куравлёв, Александр Демьяненко", "Комедия", "Мосфильм"),
    ("Операция «Ы» и другие приключения Шурика", "Леонид Гайдай", "Константин Бровин",
     "Александр Демьяненко, Георгий Вицин, Юрий Никулин", "Комедия", "Мосфильм"),
    ("Москва слезам не верит", "Владимир Меньшов", "Игорь Слабневич",
     "Вера Алентова, Алексей Баталов, Ирина Муравьёва", "Драма", "Мосфильм"),
    ("Кин-дза-дза!", "Георгий Данелия", "Павел Лебешев",
     "Станислав Любшин, Евгений Леонов, Юрий Яковлев", "Фантастика", "Мосфильм"),
]

SESSION_TIMES = [dt.time(10, 0), dt.time(13, 0), dt.time(16, 0), dt.time(19, 0), dt.time(22, 0)]
DAYS = 5


def seed(db: Session) -> None:
    """Заполняет пустую базу. Если данные уже есть — ничего не делает."""
    if db.scalar(select(User).limit(1)) is None:
        db.add_all([
            User(username="admin", password_hash=hash_password(settings.admin_password), role="admin"),
            User(username="staff", password_hash=hash_password(settings.staff_password), role="staff"),
        ])

    if db.scalar(select(Cinema).limit(1)) is None:
        cinemas = [
            Cinema(name=n, address=a, category=c, seats_count=s, halls_count=h, status=st)
            for n, a, c, s, h, st in CINEMAS
        ]
        films = [
            Film(title=t, director=d, operator=o, actors=a, genre=g, studio=s)
            for t, d, o, a, g, s in FILMS
        ]
        db.add_all(cinemas + films)

        # Расписание на несколько дней вперёд, начиная с сегодняшнего.
        # Фиксированный seed — чтобы при каждом запуске получались одинаковые данные.
        rnd = random.Random(42)
        today = dt.date.today()
        for cinema in cinemas:
            if cinema.status != "Работает":
                continue
            seats_per_hall = cinema.seats_count // cinema.halls_count
            for day in range(DAYS):
                for hall in range(1, cinema.halls_count + 1):
                    for time in SESSION_TIMES:
                        db.add(Screening(
                            cinema=cinema,
                            film=rnd.choice(films),
                            hall=hall,
                            date=today + dt.timedelta(days=day),
                            time=time,
                            price=rnd.choice([250, 300, 350, 400, 500]),
                            free_seats=rnd.randint(0, seats_per_hall),
                        ))

    db.commit()
