# Справочная служба кинотеатров

Курсовой проект, задание № 10 «Кинотеатры». Система для работников справочной службы:
хранит сведения о кинотеатрах, фильмах и репертуаре (сеансах) и отвечает на запросы о прокате фильмов.

## Технологии

| Часть       | Что используется                                       |
|-------------|--------------------------------------------------------|
| База данных | PostgreSQL 16                                          |
| Бэкенд      | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic, JWT    |
| Фронтенд    | HTML + CSS + JavaScript (без фреймворков), nginx       |
| Запуск      | Docker Compose — три контейнера: `db`, `backend`, `frontend` |

```
Браузер ──> frontend (nginx, порт 8080) ──/api/──> backend (FastAPI) ──> db (PostgreSQL)
```

## Запуск

Нужен Docker с плагином Compose.

```bash
docker compose up --build -d
```

Открыть http://localhost:8080

| Логин   | Пароль  | Права                                                    |
|---------|---------|----------------------------------------------------------|
| `admin` | `admin` | всё: добавление, изменение, удаление данных              |
| `staff` | `staff` | просмотр, запросы, продажа билетов                       |

При первом запуске база заполняется примерами: 4 кинотеатра, 8 фильмов и сеансы на 5 дней вперёд.

Документация API (Swagger): http://localhost:8080/api/docs

Остановить: `docker compose down`. Удалить вместе с данными БД: `docker compose down -v`.

Пароли и секретный ключ можно поменять в файле `.env` (образец — `.env.example`).

## Тесты

```bash
docker compose exec backend pytest -v
```

Тесты используют отдельную базу `cinema_test` и не трогают рабочие данные.

## Структура проекта

```
docker-compose.yml         описание трёх контейнеров
db/init/                   SQL, выполняемый при создании БД (база для тестов)
backend/
  app/
    main.py                создание приложения, подключение роутеров, создание таблиц
    config.py              настройки из переменных окружения
    database.py            подключение к БД, сессии
    models.py              таблицы БД (SQLAlchemy)
    schemas.py             формат входных и выходных данных API (Pydantic)
    auth.py                пароли, JWT-токены, проверка ролей
    seed.py                начальные данные
    routers/               эндпоинты API
      auth.py              вход
      cinemas.py           кинотеатры
      films.py             фильмы
      screenings.py        репертуар (сеансы) и продажа билетов
      queries.py           запросы справочной службы
  tests/                   автотесты (pytest)
frontend/
  nginx.conf               раздача страниц и пересылка /api/ в бэкенд
  public/                  index.html, style.css, app.js
```

## База данных

```
cinemas (кинотеатры)          films (фильмы)            users (работники)
  id                            id                        id
  name        название          title      название       username
  address     адрес             director   режиссёр       password_hash
  category    категория         operator   оператор       role  admin/staff
  seats_count кол. мест         actors     актёры
  halls_count кол. залов        genre      жанр
  status      состояние         studio     киностудия
       │                             │
       └──────────┐       ┌──────────┘
                  ▼       ▼
          screenings (репертуар)
            id
            cinema_id  → cinemas.id
            film_id    → films.id
            hall       номер зала
            date       дата
            time       сеанс (время)
            price      цена
            free_seats свободных мест
```

- Сеанс связан с кинотеатром и фильмом внешними ключами с `ON DELETE CASCADE`: при удалении фильма удаляются и его сеансы.
- Уникальность `(cinema_id, hall, date, time)`: в одном зале в одно время — один сеанс.
  В разных залах одного кинотеатра одновременно могут идти разные фильмы.

## Как задание соответствует API

| Требование из задания                          | Эндпоинт                                       |
|------------------------------------------------|------------------------------------------------|
| Сведения о кинотеатрах                         | `GET /api/cinemas`                             |
| Сведения о фильмах                             | `GET /api/films`                               |
| Сведения о репертуаре                          | `GET /api/screenings`                          |
| Репертуар кинотеатра                           | `GET /api/queries/repertoire/{cinema_id}`      |
| В каких кинотеатрах можно посмотреть боевики   | `GET /api/queries/cinemas-by-genre?genre=Боевик` |
| Число свободных мест на сеанс в кинотеатре     | `GET /api/queries/session?cinema_id=&date=&time=` |
| Цена билетов на сеанс в кинотеатре             | `GET /api/queries/session?cinema_id=&date=&time=` |
| Фильмы заданного режиссёра в прокате           | `GET /api/queries/films-by-director?director=` |
| В каких кинотеатрах демонстрируются комедии    | `GET /api/queries/cinemas-by-genre?genre=Комедия` |
| Добавление и удаление фильма                   | `POST /api/films`, `DELETE /api/films/{id}`    |

Кроме этого: добавление, изменение и удаление кинотеатров и сеансов (`POST`/`PUT`/`DELETE`),
продажа билетов `POST /api/screenings/{id}/sell` (уменьшает число свободных мест).

«Демонстрируются» / «в прокате» — значит, есть сеанс сегодня или позже.
