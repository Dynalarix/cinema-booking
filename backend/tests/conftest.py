import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User

# Тесты работают с отдельной базой cinema_test (см. db/init)
engine = create_engine(os.environ["TEST_DATABASE_URL"])
TestingSession = sessionmaker(bind=engine, autoflush=False)

ADMIN_HASH = hash_password("admin")
STAFF_HASH = hash_password("staff")


@pytest.fixture
def client():
    # Перед каждым тестом — чистые таблицы и два пользователя
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        db.add_all([
            User(username="admin", password_hash=ADMIN_HASH, role="admin"),
            User(username="staff", password_hash=STAFF_HASH, role="staff"),
        ])
        db.commit()

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def login(client, username):
    response = client.post("/api/auth/login", data={"username": username, "password": username})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin(client):
    return login(client, "admin")


@pytest.fixture
def staff(client):
    return login(client, "staff")
