from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Настройки приложения. Значения берутся из переменных окружения."""

    database_url: str = "postgresql+psycopg://cinema:cinema@localhost:5432/cinema"
    secret_key: str = "dev-secret-change-me"
    token_expire_minutes: int = 480
    admin_password: str = "admin"
    staff_password: str = "staff"


settings = Settings()
