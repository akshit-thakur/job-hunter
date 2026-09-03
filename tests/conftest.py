import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test.db"
    uploads_dir = tmp_path / "uploads"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    monkeypatch.setenv("UPLOADS_DIR", str(uploads_dir))
    monkeypatch.delenv("WEEKLY_TARGET", raising=False)
    import app.config
    monkeypatch.setattr(app.config, "UPLOADS_DIR", uploads_dir)
    for module_name in ("app.main", "app.routes.applications"):
        module = sys.modules.get(module_name)
        if module is not None:
            monkeypatch.setattr(module, "UPLOADS_DIR", uploads_dir)
    from app.db import init_db
    init_db()
    yield str(db_file)


@pytest.fixture()
def client(tmp_db):
    from app.main import create_app
    return TestClient(create_app(), follow_redirects=False)
