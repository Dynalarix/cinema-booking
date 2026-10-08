"""Тесты текстового ассистента.

Проверяют всё, что должен уметь ассистент из задания: распознать намерение,
достать параметры из естественного языка, вызвать правильный эндпоинт API
и вернуть осмысленный ответ.
"""

import datetime as dt

from .test_api import make_cinema, make_film, make_screening

TODAY = dt.date.today().isoformat()


def ask(client, headers, message):
    response = client.post("/api/assistant/ask", json={"message": message}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- Авторизация ---

def test_assistant_requires_login(client):
    assert client.post("/api/assistant/ask", json={"message": "привет"}).status_code == 401


# --- Распознавание отдельных параметров (slot filling) ---

def test_extract_date_time_count_genre():
    # Проверяем «мозги» ассистента напрямую — без API
    from app.assistant import (extract_count, extract_date, extract_genre,
                               extract_time)

    today = dt.date.today()
    assert extract_date("сегодня") == today
    assert extract_date("на завтра") == today + dt.timedelta(days=1)
    assert extract_date("послезавтра") == today + dt.timedelta(days=2)
    assert extract_date("10.10.2026") == dt.date(2026, 10, 10)
    assert extract_date("ничего") is None

    assert extract_time("в 19:30") == dt.time(19, 30)
    assert extract_time("в 19 часов") == dt.time(19, 0)
    assert extract_time("ничего") is None

    assert extract_count("продай 3 билета") == 3
    assert extract_count("возьми два") == 2
    assert extract_count("ничего") is None

    assert extract_genre("какие боевики идут") == "Боевик"
    assert extract_genre("комедии?") == "Комедия"
    assert extract_genre("драма") == "Драма"
    assert extract_genre("ничего") is None


# --- Намерения ---

def test_help(client, admin):
    reply = ask(client, admin, "что ты умеешь?")
    assert "умею" in reply["text"].lower()
    assert reply["rows"] == []


def test_unknown_falls_back_to_help(client, admin):
    reply = ask(client, admin, "абырвалг")
    assert "умею" in reply["text"].lower()


def test_list_cinemas(client, admin):
    make_cinema(client, admin, name="Рассвет")
    make_cinema(client, admin, name="Звезда")
    reply = ask(client, admin, "список кинотеатров")
    names = sorted(r["name"] for r in reply["rows"])
    assert names == ["Звезда", "Рассвет"]


def test_cinemas_by_genre(client, admin):
    cinema = make_cinema(client, admin, name="Звезда")
    film = make_film(client, admin, genre="Боевик")
    make_screening(client, admin, cinema, film)
    reply = ask(client, admin, "где можно посмотреть боевики?")
    assert [r["name"] for r in reply["rows"]] == ["Звезда"]


def test_cinemas_by_genre_empty(client, admin):
    reply = ask(client, admin, "где идут комедии?")
    assert "нигде нет" in reply["text"]
    assert reply["rows"] == []


def test_repertoire_by_cinema_name_in_prepositional_case(client, admin):
    """«в Рассвете» — родительный/предложный падеж, должно сработать по корню."""
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    make_screening(client, admin, cinema, film)
    reply = ask(client, admin, "что идет в Рассвете?")
    assert len(reply["rows"]) == 1
    assert reply["rows"][0]["film_title"] == "Брат"


def test_films_by_director_in_genitive(client, admin):
    """«фильмы Гайдая» — родительный падеж фамилии."""
    cinema = make_cinema(client, admin)
    film = make_film(client, admin, title="Бриллиантовая рука", director="Леонид Гайдай")
    make_screening(client, admin, cinema, film)
    reply = ask(client, admin, "фильмы Гайдая")
    assert [r["title"] for r in reply["rows"]] == ["Бриллиантовая рука"]


def test_free_seats_at_session(client, admin):
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    make_screening(client, admin, cinema, film, time="19:00:00", free_seats=42)
    reply = ask(client, admin, f"сколько свободных мест в Рассвете {TODAY} в 19:00?")
    assert "42" in reply["text"]


def test_price_at_session(client, admin):
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    make_screening(client, admin, cinema, film, time="19:00:00", price=350)
    reply = ask(client, admin, f"цена билетов в Рассвете {TODAY} в 19:00")
    assert "350" in reply["text"]


def test_sell_tickets_reduces_free_seats(client, admin):
    """Главный «агентский» сценарий: ассистент сам находит сеанс и продаёт билеты."""
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    screening = make_screening(client, admin, cinema, film, time="19:00:00",
                               free_seats=10).json()
    reply = ask(client, admin, f"продай 3 билета в Рассвете {TODAY} 19:00")
    assert "Продано 3" in reply["text"]
    # Проверяем через настоящий API, что места действительно уменьшились
    remaining = client.get(f"/api/screenings/{screening['id']}", headers=admin).json()
    assert remaining["free_seats"] == 7


def test_sell_rejects_without_free_seats(client, admin):
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    make_screening(client, admin, cinema, film, time="19:00:00", free_seats=2)
    reply = ask(client, admin, f"продай 5 билетов в Рассвете {TODAY} 19:00")
    assert "свободно только 2" in reply["text"]


def test_sell_asks_for_missing_fields(client, admin):
    reply = ask(client, admin, "продай билет")
    # Нет ни кинотеатра, ни времени — ассистент просит уточнить
    assert "кинотеатр" in reply["text"].lower()
    assert "время" in reply["text"].lower()


def test_assistant_respects_staff_permissions(client, staff, admin):
    """Если у сотрудника нет прав — внутренний вызов API не удастся.

    Админские операции (DELETE и т.п.) ассистент не делает, но мы всё равно
    убеждаемся, что продажа билетов — которую имеет право делать и staff —
    работает под его токеном.
    """
    cinema = make_cinema(client, admin, name="Рассвет")
    film = make_film(client, admin)
    make_screening(client, admin, cinema, film, time="19:00:00", free_seats=5)
    reply = ask(client, staff, f"продай 2 билета в Рассвете {TODAY} 19:00")
    assert "Продано 2" in reply["text"]
