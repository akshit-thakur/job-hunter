import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.delenv("WEEKLY_TARGET", raising=False)
    from app.db import init_db
    init_db()
    yield str(db_file)


@pytest.fixture()
def client(tmp_db):
    from app.main import create_app
    return TestClient(create_app(), follow_redirects=False)
