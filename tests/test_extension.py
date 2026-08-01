import json
from io import BytesIO
from zipfile import ZipFile

from app.config import PROJECT_ROOT
from app.routes.extensions import EXTENSION_FILES


def test_zen_extension_package(client):
    response = client.get("/extension/zen.zip")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "job-tracker-zen-extension.zip" in response.headers["content-disposition"]

    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == set(EXTENSION_FILES)
        manifest = json.loads(archive.read("manifest.json"))
        popup = archive.read("popup.js").decode()

    assert manifest["manifest_version"] == 3
    assert manifest["action"]["default_popup"] == "popup.html"
    assert manifest["commands"]["_execute_action"]["suggested_key"]["default"] == "Alt+Shift+J"
    assert manifest["host_permissions"] == [
        "http://127.0.0.1:9000/*",
        "http://localhost:9000/*",
    ]
    assert "content_scripts" not in manifest
    assert "tabs" not in manifest.get("permissions", [])
    assert 'fetchJson("/applications"' in popup


def test_docker_image_includes_extension_source():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    assert "COPY extensions/ extensions/" in dockerfile
