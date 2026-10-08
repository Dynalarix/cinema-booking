from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import Base, SessionLocal, engine
from app.routers import assistant, auth, cinemas, films, queries, screenings
from app.seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При запуске: создать таблицы (если их ещё нет) и заполнить начальными данными
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(
    title="Справочная служба кинотеатров",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.include_router(auth.router)
app.include_router(cinemas.router)
app.include_router(films.router)
app.include_router(screenings.router)
app.include_router(queries.router)
app.include_router(assistant.router)
