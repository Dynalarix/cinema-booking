import datetime as dt

TODAY = dt.date.today().isoformat()
YESTERDAY = (dt.date.today() - dt.timedelta(days=1)).isoformat()


def make_cinema(client, headers, **overrides):
    data = {"name": "Рассвет", "address": "ул. Ленина, 1", "category": "Высшая",
            "seats_count": 300, "halls_count": 2, "status": "Работает"} | overrides
    response = client.post("/api/cinemas", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def make_film(client, headers, **overrides):
    data = {"title": "Брат", "director": "Алексей Балабанов", "operator": "Сергей Астахов",
            "actors": "Сергей Бодров-мл.", "genre": "Боевик", "studio": "СТВ"} | overrides
    response = client.post("/api/films", json=data, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def make_screening(client, headers, cinema, film, **overrides):
    data = {"cinema_id": cinema["id"], "film_id": film["id"], "hall": 1, "date": TODAY,
            "time": "19:00:00", "price": 350, "free_seats": 100} | overrides
    return client.post("/api/screenings", json=data, headers=headers)


# --- Авторизация и права ---

def test_login_with_wrong_password(client):
    response = client.post("/api/auth/login", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 401


def test_requests_without_token_are_rejected(client):
    assert client.get("/api/films").status_code == 401


def test_me_returns_role(client, staff):
    assert client.get("/api/auth/me", headers=staff).json() == {"username": "staff", "role": "staff"}


def test_staff_can_read_but_not_modify(client, admin, staff):
    make_film(client, admin)
    assert client.get("/api/films", headers=staff).status_code == 200
    film = {"title": "X", "director": "X", "operator": "X", "actors": "X", "genre": "Драма", "studio": "X"}
    assert client.post("/api/films", json=film, headers=staff).status_code == 403


# --- Добавление, изменение и удаление ---

def test_add_update_and_delete_film(client, admin):
    film = make_film(client, admin)
    response = client.put(f"/api/films/{film['id']}", json=film | {"genre": "Драма"}, headers=admin)
    assert response.json()["genre"] == "Драма"

    assert client.delete(f"/api/films/{film['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/films/{film['id']}", headers=admin).status_code == 404


def test_deleting_film_deletes_its_screenings(client, admin):
    cinema, film = make_cinema(client, admin), make_film(client, admin)
    make_screening(client, admin, cinema, film)
    client.delete(f"/api/films/{film['id']}", headers=admin)
    assert client.get("/api/screenings", headers=admin).json() == []


def test_invalid_data_is_rejected(client, admin):
    response = client.post("/api/cinemas", json={"name": "", "seats_count": -1}, headers=admin)
    assert response.status_code == 422


def test_screening_hall_must_exist(client, admin):
    cinema, film = make_cinema(client, admin, halls_count=2), make_film(client, admin)
    assert make_screening(client, admin, cinema, film, hall=3).status_code == 400


def test_two_screenings_in_same_hall_at_same_time(client, admin):
    cinema, film = make_cinema(client, admin), make_film(client, admin)
    assert make_screening(client, admin, cinema, film).status_code == 201
    assert make_screening(client, admin, cinema, film).status_code == 409


# --- Продажа билетов ---

def test_sell_tickets(client, admin, staff):
    cinema, film = make_cinema(client, admin), make_film(client, admin)
    screening = make_screening(client, admin, cinema, film, free_seats=5).json()
    url = f"/api/screenings/{screening['id']}/sell"

    response = client.post(url, json={"count": 3}, headers=staff)
    assert response.json()["free_seats"] == 2

    response = client.post(url, json={"count": 3}, headers=staff)
    assert response.status_code == 409
    assert client.get(f"/api/screenings/{screening['id']}", headers=staff).json()["free_seats"] == 2


# --- Запросы справочной службы ---

def test_cinema_repertoire_shows_only_upcoming(client, admin):
    cinema, film = make_cinema(client, admin), make_film(client, admin)
    make_screening(client, admin, cinema, film, date=TODAY)
    make_screening(client, admin, cinema, film, date=YESTERDAY)
    rows = client.get(f"/api/queries/repertoire/{cinema['id']}", headers=admin).json()
    assert [r["date"] for r in rows] == [TODAY]


def test_cinemas_by_genre(client, admin):
    action_cinema = make_cinema(client, admin, name="Звезда")
    comedy_cinema = make_cinema(client, admin, name="Спутник")
    action = make_film(client, admin, genre="Боевик")
    comedy = make_film(client, admin, title="Бриллиантовая рука", genre="Комедия")
    make_screening(client, admin, action_cinema, action)
    make_screening(client, admin, action_cinema, action, time="21:00:00")
    make_screening(client, admin, comedy_cinema, comedy)

    rows = client.get("/api/queries/cinemas-by-genre", params={"genre": "боевик"}, headers=admin).json()
    assert [r["name"] for r in rows] == ["Звезда"]
    rows = client.get("/api/queries/cinemas-by-genre", params={"genre": "Комедия"}, headers=admin).json()
    assert [r["name"] for r in rows] == ["Спутник"]


def test_session_free_seats_and_price(client, admin):
    cinema, film = make_cinema(client, admin), make_film(client, admin)
    make_screening(client, admin, cinema, film, time="19:00:00", price=400, free_seats=42)
    params = {"cinema_id": cinema["id"], "date": TODAY, "time": "19:00"}
    rows = client.get("/api/queries/session", params=params, headers=admin).json()
    assert [(r["free_seats"], r["price"]) for r in rows] == [(42, 400)]


def test_films_by_director_only_shown_ones(client, admin):
    cinema = make_cinema(client, admin)
    shown = make_film(client, admin, title="Брат")
    make_film(client, admin, title="Груз 200")  # без сеансов — не должен попасть
    make_screening(client, admin, cinema, shown)

    rows = client.get("/api/queries/films-by-director", params={"director": "балабанов"}, headers=admin).json()
    assert [r["title"] for r in rows] == ["Брат"]
