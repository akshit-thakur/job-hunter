"""Tests for the JSON API used by the macOS menu-bar client."""

from app.queries import create_application


def _app_data(**overrides):
    base = {
        "company": "ApiCo",
        "role_title": "Engineer",
        "location": None,
        "work_mode": "remote",
        "source": "linkedin",
        "jd_url": None,
        "salary_min": None,
        "salary_max": None,
        "status": "applied",
        "resume_version": None,
        "applied_date": "2026-08-01",
        "follow_up_date": None,
        "notes": None,
    }
    return {**base, **overrides}


def test_stats_empty(client):
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] == 0
    assert body["interviewing"] == 0
    assert body["active"] == 0
    assert body["total"] == 0
    assert "submitted_this_week" in body
    assert "weekly_target" in body
    assert "followups_due" in body


def test_stats_counts(client, tmp_db):
    create_application(_app_data(company="A", status="applied"))
    create_application(_app_data(company="B", status="hr_screen"))
    create_application(_app_data(company="C", status="tech_round"))
    create_application(_app_data(company="D", status="saved", applied_date=None))
    create_application(_app_data(company="E", status="rejected"))

    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    # applied = everything except saved
    assert body["applied"] == 4
    # interviewing = hr_screen + tech_round + final_round
    assert body["interviewing"] == 2
    # active = not offer/rejected/withdrawn
    assert body["active"] == 4
    assert body["total"] == 5


def test_post_application_creates_row(client):
    resp = client.post(
        "/applications",
        json={
            "company": "MenuBar Co",
            "role": "iOS Engineer",
            "url": "https://example.com/jobs/1",
            "status": "applied",
            "notes": "From menu bar",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] >= 1
    assert body["company"] == "MenuBar Co"
    assert body["role"] == "iOS Engineer"
    assert body["url"] == "https://example.com/jobs/1"
    assert body["status"] == "applied"
    assert body["notes"] == "From menu bar"

    stats = client.get("/stats").json()
    assert stats["applied"] == 1
    assert stats["total"] == 1


def test_post_application_defaults_status(client):
    resp = client.post(
        "/applications",
        json={"company": "DefaultCo", "role": "Backend"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "applied"


def test_post_application_trims_compact_form_values(client):
    resp = client.post(
        "/applications",
        json={
            "company": "  Trim Co  ",
            "role": "  Engineer  ",
            "url": "  https://example.com/job  ",
            "notes": "  Follow up Friday  ",
        },
    )
    assert resp.status_code == 201
    assert resp.json() == {
        "id": resp.json()["id"],
        "company": "Trim Co",
        "role": "Engineer",
        "url": "https://example.com/job",
        "status": "applied",
        "notes": "Follow up Friday",
    }


def test_post_application_validation_error(client):
    resp = client.post(
        "/applications",
        json={"company": "", "role": "Engineer"},
    )
    assert resp.status_code == 422


def test_post_application_invalid_status(client):
    resp = client.post(
        "/applications",
        json={"company": "X", "role": "Y", "status": "not_a_status"},
    )
    assert resp.status_code == 422


def test_get_applications_html_still_works(client):
    """POST /applications is JSON; GET /applications remains the HTML list."""
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert b"Applications" in resp.content
