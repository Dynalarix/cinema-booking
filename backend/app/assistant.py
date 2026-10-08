"""Текстовый ассистент справочной службы.

Разбирает запросы на естественном языке (например, «репертуар Рассвета»,
«фильмы Гайдая», «продай 2 билета в Звезде на завтра 19:00») и вызывает
подходящий эндпоинт REST API. К базе данных напрямую не обращается — это
обеспечивает безопасность: ассистент работает только через API и получает
ровно те же права, что и вошедший сотрудник (по его JWT-токену).

Устройство модуля:

1. Нормализация текста (lower-case, замена «ё» на «е», удаление лишних
   знаков) — чтобы одинаково реагировать на «БОЕВИКИ?» и «боевики».
2. Извлечение параметров (slot filling) — функции extract_* достают из
   запроса дату, время, жанр, число билетов, название кинотеатра,
   фамилию режиссёра. Поиск по названиям — с учётом русских падежей
   (сравнивается общий корень слова).
3. Определение намерения (intent recognition) — список try_* функций,
   каждая проверяет свои ключевые слова. Первая подошедшая обрабатывает
   запрос. Порядок важен: сначала более специфичные (продажа, цена),
   потом общие (список).
4. Вызов API — класс Assistant держит httpx-клиент с JWT пользователя и
   делает HTTP-запросы к собственному серверу.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx


# ----------------------------------------------------------------------
# Нормализация текста
# ----------------------------------------------------------------------

def normalize(text: str) -> str:
    """Приводит текст к виду, удобному для сравнения.

    Пример: «  Что идёт в Рассвете? » → «что идет в рассвете».
    """
    text = text.lower().replace("ё", "е")
    # Оставляем буквы, цифры, двоеточие (для времени), точку и дефис (для дат)
    text = re.sub(r"[^\w\s:.\-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------
# Извлечение параметров (slot filling)
# ----------------------------------------------------------------------

# Жанры: канонический вид → корень слова (чтобы ловить «боевики», «боевика», ...)
GENRES: list[tuple[str, str]] = [
    ("Боевик", "боевик"),
    ("Комедия", "комеди"),
    ("Драма", "драм"),
    ("Фантастика", "фантастик"),
    ("Мелодрама", "мелодрам"),
    ("Триллер", "триллер"),
    ("Ужасы", "ужас"),
    ("Мультфильм", "мультф"),
]

# Корни месяцев в родительном падеже: «10 октября» → 10
MONTH_STEMS: list[tuple[str, int]] = [
    ("январ", 1), ("феврал", 2), ("март", 3), ("апрел", 4),
    ("июн", 6), ("июл", 7), ("август", 8), ("сентябр", 9),
    ("октябр", 10), ("ноябр", 11), ("декабр", 12),
    # «май» ловим отдельно — корень слишком короткий и совпадает с другими словами
]

NUMBER_WORDS: dict[str, int] = {
    "один": 1, "одного": 1, "одну": 1, "два": 2, "две": 2, "двух": 2,
    "три": 3, "трех": 3, "четыре": 4, "четырех": 4, "пять": 5, "пяти": 5,
    "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
}


def extract_genre(norm: str) -> str | None:
    for canonical, stem in GENRES:
        if stem in norm:
            return canonical
    return None


def extract_date(norm: str) -> dt.date | None:
    """«сегодня» / «завтра» / «послезавтра» / «10.10.2026» / «10 октября» / «2026-10-10»."""
    today = dt.date.today()
    if "послезавтра" in norm:
        return today + dt.timedelta(days=2)
    if "завтра" in norm:
        return today + dt.timedelta(days=1)
    if "сегодня" in norm:
        return today

    # «10.10.2026», «10.10.26», «10.10»
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b", norm)
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            return dt.date(year, month, day)
        except ValueError:
            pass

    # «2026-10-10»
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", norm)
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # «10 октября»
    for stem, month in MONTH_STEMS:
        m = re.search(rf"\b(\d{{1,2}})\s+{stem}", norm)
        if m:
            day = int(m.group(1))
            try:
                date = dt.date(today.year, month, day)
                # Если дата уже прошла в этом году — считаем, что имеется в виду следующий
                if date < today:
                    date = dt.date(today.year + 1, month, day)
                return date
            except ValueError:
                pass

    # «10 мая» — обрабатываем отдельно, корень «ма» слишком общий
    m = re.search(r"\b(\d{1,2})\s+ма[йя]", norm)
    if m:
        day = int(m.group(1))
        try:
            date = dt.date(today.year, 5, day)
            if date < today:
                date = dt.date(today.year + 1, 5, day)
            return date
        except ValueError:
            pass

    return None


def extract_time(norm: str) -> dt.time | None:
    """«19:00» или «19 часов»."""
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", norm)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if 0 <= hour < 24 and 0 <= minute < 60:
            return dt.time(hour, minute)

    m = re.search(r"\b(\d{1,2})\s*час", norm)
    if m:
        hour = int(m.group(1))
        if 0 <= hour < 24:
            return dt.time(hour, 0)

    return None


def extract_count(norm: str) -> int | None:
    """Число билетов: «2 билета», «продай 3», «пять» и т.п."""
    m = re.search(r"\b(\d{1,3})\s*билет", norm)
    if m:
        return int(m.group(1))
    for word, number in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", norm):
            return number
    m = re.search(r"\b(?:продай|купи|забронируй|возьми|бронь)\b.*?\b(\d{1,3})\b", norm)
    if m:
        return int(m.group(1))
    return None


def extract_by_name(
    norm: str, items: list[dict], key: str, stem_len: int = 5
) -> dict | None:
    """Ищет в тексте элемент по совпадению его названия.

    Сначала пробует полное совпадение (без учёта регистра), затем — по корню
    (первые stem_len букв), чтобы ловить русские падежи:
    «в Рассвете» → stem «рассв» ⊂ «в рассвете».
    Из нескольких подходящих выбирает элемент с самым длинным названием.
    """
    sorted_items = sorted(items, key=lambda x: -len(x[key]))

    for item in sorted_items:
        name = normalize(item[key])
        if name and name in norm:
            return item

    for item in sorted_items:
        name = normalize(item[key])
        stem = name[: min(len(name), stem_len)]
        if len(stem) >= 4 and stem in norm:
            return item
    return None


def extract_director(norm: str, films: list[dict]) -> str | None:
    """Ищет в тексте фамилию режиссёра из списка известных.

    Режиссёры хранятся как «Имя Фамилия», в запросе обычно только фамилия
    и часто в родительном падеже («Гайдая»). Сравниваем по корню фамилии.
    """
    directors = sorted({f["director"] for f in films}, key=lambda d: -len(d))
    for director in directors:
        surname = director.split()[-1]
        surname_norm = normalize(surname)
        if surname_norm in norm:
            return director
        stem = surname_norm[: min(len(surname_norm), 5)]
        if len(stem) >= 4 and stem in norm:
            return director
    return None


# ----------------------------------------------------------------------
# Ответ ассистента
# ----------------------------------------------------------------------

@dataclass
class Column:
    field: str
    title: str


@dataclass
class Reply:
    """Что ассистент возвращает фронтенду: короткий текст и опционально таблица."""

    text: str
    columns: list[Column] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "columns": [{"field": c.field, "title": c.title} for c in self.columns],
            "rows": self.rows,
        }


# ----------------------------------------------------------------------
# Основной класс — обёртка над httpx и диспетчер намерений
# ----------------------------------------------------------------------

Handler = Callable[["Assistant", str, str], Awaitable["Reply | None"]]


class Assistant:
    """Выполняет один запрос пользователя.

    Создаётся на один HTTP-запрос фронтенда: получает httpx-клиент
    (с ASGI-транспортом к собственному приложению) и JWT пользователя.
    Списки кинотеатров и фильмов подгружает по требованию и кэширует.
    """

    def __init__(self, http: httpx.AsyncClient, token: str) -> None:
        self._http = http
        self._auth = {"Authorization": f"Bearer {token}"}
        self._cinemas: list[dict] | None = None
        self._films: list[dict] | None = None

    async def _get(self, path: str, **params) -> list[dict] | dict:
        response = await self._http.get(path, params=params, headers=self._auth)
        response.raise_for_status()
        return response.json()

    async def _post(self, path: str, json: dict) -> httpx.Response:
        return await self._http.post(path, json=json, headers=self._auth)

    async def cinemas(self) -> list[dict]:
        if self._cinemas is None:
            self._cinemas = await self._get("/api/cinemas")  # type: ignore[assignment]
        return self._cinemas  # type: ignore[return-value]

    async def films(self) -> list[dict]:
        if self._films is None:
            self._films = await self._get("/api/films")  # type: ignore[assignment]
        return self._films  # type: ignore[return-value]

    async def ask(self, text: str) -> Reply:
        """Главный метод: подбирает подходящий обработчик и возвращает ответ."""
        norm = normalize(text)
        if not norm:
            return help_reply()
        for handler in HANDLERS:
            reply = await handler(self, norm, text)
            if reply is not None:
                return reply
        return help_reply()


# ----------------------------------------------------------------------
# Форматирование полей для вывода (чтобы не возиться на фронтенде)
# ----------------------------------------------------------------------

def _format_date(iso: str) -> str:
    """2026-10-10 → 10.10.2026."""
    try:
        return dt.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return iso


def _format_time(iso: str) -> str:
    """19:00:00 → 19:00."""
    return iso[:5] if isinstance(iso, str) and len(iso) >= 5 else str(iso)


def _format_rows(rows: list[dict]) -> list[dict]:
    """Приводит даты и время к читаемому виду, остальные поля оставляет как есть."""
    out = []
    for row in rows:
        formatted = dict(row)
        if "date" in formatted:
            formatted["date"] = _format_date(formatted["date"])
        if "time" in formatted:
            formatted["time"] = _format_time(formatted["time"])
        out.append(formatted)
    return out


# ----------------------------------------------------------------------
# Обработчики намерений (intent handlers)
#
# Каждый try_* проверяет свои ключевые слова и либо возвращает Reply,
# либо None — тогда диспетчер переходит к следующему обработчику.
# Порядок в HANDLERS важен: более специфичные намерения проверяются первыми.
# ----------------------------------------------------------------------

HELP_LINES = [
    "«репертуар <кинотеатр>» — расписание сеансов кинотеатра",
    "«где идут боевики / комедии / драмы» — кинотеатры по жанру",
    "«фильмы Гайдая» — фильмы режиссёра, которые сейчас в прокате",
    "«сколько мест в <кинотеатр> <дата> в <время>» — свободные места",
    "«цена билетов в <кинотеатр> <дата> в <время>» — цена",
    "«продай N билетов в <кинотеатр> на <дата> <время>» — продажа билетов",
    "«список кинотеатров», «список фильмов»",
]


def help_reply() -> Reply:
    text = (
        "Я помогаю работать со справочной службой. Умею:\n• "
        + "\n• ".join(HELP_LINES)
        + "\n\nДаты можно писать так: сегодня, завтра, послезавтра, "
        "10.10.2026, 10 октября. Время — так: 19:00 или «в 19 часов»."
    )
    return Reply(text=text)


async def try_help(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if re.search(r"\b(помощ|помоги|что ты умеешь|что можешь|команд|что делаеш)", norm):
        return help_reply()
    return None


async def try_list_cinemas(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if not re.search(r"\b(список|все|какие|перечень|покажи)\b.*\bкинотеатр", norm):
        return None
    cinemas = await assistant.cinemas()
    return Reply(
        text=f"Всего кинотеатров: {len(cinemas)}.",
        columns=[Column("name", "Название"), Column("address", "Адрес"),
                 Column("category", "Категория"), Column("status", "Состояние")],
        rows=cinemas,
    )


async def try_list_films(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if not re.search(r"\b(список|все|какие|перечень|покажи)\b.*\bфильм", norm):
        return None
    films = await assistant.films()
    return Reply(
        text=f"Всего фильмов в базе: {len(films)}.",
        columns=[Column("title", "Название"), Column("director", "Режиссёр"),
                 Column("genre", "Жанр"), Column("studio", "Киностудия")],
        rows=films,
    )


async def try_sell(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if not re.search(r"\b(продай|купи|забронируй|возьми|бронь|продать|купить|продажа)\b", norm):
        return None

    cinemas = await assistant.cinemas()
    cinema = extract_by_name(norm, cinemas, "name")
    date = extract_date(norm) or dt.date.today()
    time = extract_time(norm)
    count = extract_count(norm)

    missing = []
    if cinema is None:
        missing.append("кинотеатр")
    if time is None:
        missing.append("время сеанса")
    if count is None:
        missing.append("число билетов")
    if missing:
        return Reply(text=(
            "Чтобы продать билеты, нужны: " + ", ".join(missing) + ". "
            "Например: «продай 2 билета в Рассвете на завтра 19:00»."
        ))

    assert cinema is not None and time is not None and count is not None
    sessions = await assistant._get(
        "/api/queries/session",
        cinema_id=cinema["id"],
        date=date.isoformat(),
        time=time.strftime("%H:%M:%S"),
    )
    if not sessions:
        return Reply(text=(
            f"В «{cinema['name']}» на {date.strftime('%d.%m.%Y')} "
            f"в {time.strftime('%H:%M')} сеансов нет."
        ))

    # Берём первый сеанс (зал), в котором хватает мест
    enough = [s for s in sessions if s["free_seats"] >= count]
    if not enough:
        best = max(s["free_seats"] for s in sessions)
        return Reply(text=(
            f"На сеансе {date.strftime('%d.%m.%Y')} {time.strftime('%H:%M')} "
            f"в «{cinema['name']}» свободно только {best} мест, а нужно {count}."
        ))

    chosen = enough[0]
    response = await assistant._post(
        f"/api/screenings/{chosen['id']}/sell", {"count": count}
    )
    if response.status_code != 200:
        detail = response.json().get("detail", "ошибка")
        return Reply(text=f"Не удалось продать билеты: {detail}")

    screening = response.json()
    return Reply(text=(
        f"Продано {count} билет(ов) на фильм «{chosen['film_title']}» в "
        f"«{cinema['name']}», зал {chosen['hall']}, "
        f"{date.strftime('%d.%m.%Y')} в {time.strftime('%H:%M')}. "
        f"Осталось свободных мест: {screening['free_seats']}."
    ))


async def _session_query(
    assistant: Assistant, norm: str, info: str
) -> Reply | None:
    cinemas = await assistant.cinemas()
    cinema = extract_by_name(norm, cinemas, "name")
    date = extract_date(norm) or dt.date.today()
    time = extract_time(norm)
    if cinema is None or time is None:
        example = (
            "«сколько мест в Рассвете завтра в 19:00»"
            if info == "free_seats"
            else "«цена билетов в Рассвете завтра в 19:00»"
        )
        return Reply(text=f"Нужны кинотеатр и время сеанса. Например: {example}.")

    sessions = await assistant._get(
        "/api/queries/session",
        cinema_id=cinema["id"],
        date=date.isoformat(),
        time=time.strftime("%H:%M:%S"),
    )
    if not sessions:
        return Reply(text=(
            f"В «{cinema['name']}» на {date.strftime('%d.%m.%Y')} "
            f"в {time.strftime('%H:%M')} сеансов нет."
        ))

    if info == "free_seats":
        total = sum(s["free_seats"] for s in sessions)
        head = (
            f"В «{cinema['name']}» {date.strftime('%d.%m.%Y')} в "
            f"{time.strftime('%H:%M')} свободных мест всего: {total}."
        )
        columns = [Column("hall", "Зал"), Column("film_title", "Фильм"),
                   Column("free_seats", "Свободных мест")]
    else:  # price
        prices = sorted({s["price"] for s in sessions})
        price_str = ", ".join(f"{p} ₽" for p in prices)
        head = (
            f"Цена билетов на {date.strftime('%d.%m.%Y')} в "
            f"{time.strftime('%H:%M')} в «{cinema['name']}»: {price_str}."
        )
        columns = [Column("hall", "Зал"), Column("film_title", "Фильм"),
                   Column("price", "Цена, ₽")]

    return Reply(text=head, columns=columns, rows=sessions)


async def try_free_seats(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if re.search(r"\bсвободн", norm) or re.search(r"сколько\s+(?:ещё\s+)?(?:есть\s+)?мест", norm):
        return await _session_query(assistant, norm, "free_seats")
    return None


async def try_price(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if re.search(r"\b(цена|стоит|стоимость|почем|сколько\s+стоит)\b", norm):
        return await _session_query(assistant, norm, "price")
    return None


async def try_repertoire(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    if not re.search(r"\b(репертуар|расписание|что\s+идет\s+в|программа)\b", norm):
        return None
    cinemas = await assistant.cinemas()
    cinema = extract_by_name(norm, cinemas, "name")
    if cinema is None:
        return Reply(text="Укажите кинотеатр. Например: «репертуар Рассвета».")
    rows = await assistant._get(f"/api/queries/repertoire/{cinema['id']}")
    if not rows:
        return Reply(text=f"В «{cinema['name']}» на ближайшие дни сеансов нет.")
    return Reply(
        text=f"Репертуар «{cinema['name']}» — сеансов: {len(rows)}.",
        columns=[Column("date", "Дата"), Column("time", "Сеанс"),
                 Column("film_title", "Фильм"), Column("hall", "Зал"),
                 Column("price", "Цена, ₽"), Column("free_seats", "Свободных мест")],
        rows=_format_rows(rows),  # type: ignore[arg-type]
    )


async def try_films_by_director(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    # Явные ключи — всегда ловим
    explicit = re.search(r"\b(режисс|снял|снимал|поставил)\b", norm)
    # Либо «фильмы <фамилия>»: сам список режиссёров подскажет, кого искать
    films = await assistant.films()
    director = extract_director(norm, films)
    implicit = director is not None and re.search(r"\bфильм", norm) is not None

    if not (explicit or implicit):
        return None

    if director is None:
        return Reply(text=(
            "Укажите фамилию режиссёра из нашей базы. "
            "Например: «фильмы Гайдая» или «что снял Балабанов»."
        ))

    rows = await assistant._get("/api/queries/films-by-director", director=director)
    if not rows:
        return Reply(text=f"Фильмов режиссёра «{director}» сейчас в прокате нет.")
    return Reply(
        text=f"Фильмы режиссёра «{director}» в прокате — {len(rows)} шт.:",
        columns=[Column("title", "Название"), Column("genre", "Жанр"),
                 Column("studio", "Киностудия")],
        rows=rows,
    )


async def try_cinemas_by_genre(assistant: Assistant, norm: str, raw: str) -> Reply | None:
    genre = extract_genre(norm)
    if genre is None:
        return None
    rows = await assistant._get("/api/queries/cinemas-by-genre", genre=genre)
    if not rows:
        return Reply(text=f"В ближайшие дни фильмов жанра «{genre}» нигде нет.")
    return Reply(
        text=f"Жанр «{genre}» идёт в {len(rows)} кинотеатр(ах):",
        columns=[Column("name", "Кинотеатр"), Column("address", "Адрес")],
        rows=rows,
    )


# Порядок намерений важен: сначала специфичные (продажа), в конце — общие (жанр).
HANDLERS: list[Handler] = [
    try_help,
    try_sell,
    try_free_seats,
    try_price,
    try_repertoire,
    try_films_by_director,
    try_list_cinemas,
    try_list_films,
    try_cinemas_by_genre,
]
