from app.queries import (
    create_application,
    duplicate_application_template,
    get_application,
)


def _app_data(**overrides):
    base = {
        "company": "DupCo",
        "role_title": "Engineer",
        "location": "Remote",
        "work_mode": "remote",
        "source": "linkedin",
        "jd_url": "https://example.com/jobs/1",
        "salary_min": 100000.0,
        "salary_max": 150000.0,
        "status": "applied",
        "job_description": "Build backend services in Python.",
        "applied_date": "2026-08-01",
        "follow_up_date": None,
        "notes": "LinkedIn Easy Apply",
    }
    return {**base, **overrides}


def test_duplicate_application_template_copies_everything_except_company_and_jd(client, tmp_db):
    app_id = create_application(_app_data())
    result = duplicate_application_template(app_id)
    assert result is not None
    application, duplicate_from = result
    assert application["company"] == ""
    assert application["jd_url"] == ""
    assert application["role_title"] == "Engineer"
    assert application["location"] == "Remote"
    assert application["source"] == "linkedin"
    assert application["work_mode"] == "remote"
    assert application["job_description"] == "Build backend services in Python."
    assert application["notes"] == "LinkedIn Easy Apply"
    assert application["status"] == "applied"
    assert application["applied_date"] == "2026-08-01"
    assert application["salary_min"] == 100000.0
    assert application["salary_max"] == 150000.0
    assert duplicate_from["id"] == app_id


def test_duplicate_route_renders_form(client, tmp_db):
    app_id = create_application(_app_data(company="PortalCo"))
    resp = client.get(f"/applications/{app_id}/duplicate")
    assert resp.status_code == 200
    assert 'action="/applications/new"' in resp.text
    assert b"Profile copied from" in resp.content
    assert b"PortalCo" in resp.content
    assert b"linkedin" in resp.content


def test_new_application_from_query_param(client, tmp_db):
    app_id = create_application(_app_data(company="QueryCo", source="job_board"))
    resp = client.get(f"/applications/new?from_id={app_id}")
    assert resp.status_code == 200
    assert b"QueryCo" in resp.content
    assert b"job_board" in resp.content


def test_duplicate_missing_application_returns_404(client):
    resp = client.get("/applications/99999/duplicate")
    assert resp.status_code == 404


def test_duplicate_url_post_creates_new_application(client, tmp_db):
    app_id = create_application(_app_data(company="SourceCo"))
    resp = client.post(f"/applications/{app_id}/duplicate")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/applications/")
    assert resp.headers["location"].endswith("/edit")

    duplicated_id = int(resp.headers["location"].split("/")[2])
    assert duplicated_id != app_id
    duplicated = get_application(duplicated_id)
    assert duplicated is not None
    assert duplicated["company"] == ""
    assert duplicated["jd_url"] == ""
    assert duplicated["role_title"] == "Engineer"
    assert duplicated["source"] == "linkedin"
    assert duplicated["job_description"] == "Build backend services in Python."


def test_duplicate_last_keyboard_hint_on_new_form(client, tmp_db):
    app_id = create_application(_app_data(company="ShortcutCo"))
    resp = client.get("/applications/new")
    assert resp.status_code == 200
    assert f'data-duplicate-last-url="/applications/{app_id}/duplicate"' in resp.text
    assert b"Duplicate from" in resp.content
    assert b">D</kbd>" in resp.content or b"\xe2\x87\xa7" in resp.content


def test_duplicate_last_keyboard_hint_on_list(client, tmp_db):
    app_id = create_application(_app_data(company="ListCo"))
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert f'data-duplicate-last-url="/applications/{app_id}/duplicate"' in resp.text
    assert b"duplicate last" in resp.content.lower()


def test_duplicate_last_url_absent_when_empty(client):
    resp = client.get("/applications/new")
    assert resp.status_code == 200
    assert "data-duplicate-last-url" not in resp.text
