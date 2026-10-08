"""Эндпоинт текстового ассистента: /api/assistant/ask.

Фронтенд присылает фразу на естественном языке и JWT-токен сотрудника.
Ассистент разбирает фразу (см. app/assistant.py) и обращается к API
кинотеатра через httpx с ASGI-транспортом — то есть делает настоящий
HTTP-запрос, но внутри процесса, без выхода в сеть.

Важно: внутренний httpx-клиент передаёт тот же токен, что получил
ассистент. Благодаря этому права пользователя (admin/staff) соблюдаются
автоматически: все проверки сделает уже вызываемый эндпоинт.
"""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, Field

import httpx

from app.assistant import Assistant
from app.auth import get_current_user
from app.models import User

router = APIRouter(prefix="/api/assistant", tags=["Ассистент"])

# OAuth2PasswordBearer можно переиспользовать как источник «сырого» токена
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


class ColumnOut(BaseModel):
    field: str
    title: str


class AskOut(BaseModel):
    text: str
    columns: list[ColumnOut] = []
    rows: list[dict] = []


@router.post("/ask", response_model=AskOut)
async def ask(
    data: AskIn,
    token: str = Depends(oauth2_scheme),
    user: User = Depends(get_current_user),  # noqa: ARG001  — только для проверки авторизации
) -> dict:
    """Разобрать фразу пользователя и выполнить соответствующий API-запрос."""
    # Импорт здесь, чтобы не создавать круговую зависимость с app.main
    from app.main import app

    # ASGITransport прогоняет HTTP-запрос через наше приложение в этом же
    # процессе — проходят все проверки авторизации, валидации и зависимости
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://assistant") as http:
        assistant = Assistant(http, token)
        reply = await assistant.ask(data.message)

    return reply.to_dict()
