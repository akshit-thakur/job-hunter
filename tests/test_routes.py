import csv
from io import StringIO

from app.queries import create_application


def _app_data(**overrides):
    base = {
        "company": "RouteCo",
        "role_title": "Tester",
        "location": None,
        "work_mode": "remote",
        "source": "linkedin",
        "jd_url": None,
        "salary_min": None,
        "salary_max": None,
        "status": "saved",
        "resume_version": None,
        "applied_date": None,
        "follow_up_date": None,
        "notes": None,
    }
    return {**base, **overrides}


def test_dashboard_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.content


def test_dashboard_renders_location_and_work_mode_breakdowns(client, tmp_db):
    create_application(_app_data(location="Bangalore", work_mode="remote"))
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Location Breakdown" in resp.content
    assert b"Work Mode Breakdown" in resp.content
    assert b"Resume Version Breakdown" not in resp.content
    assert b"Closed Applications" in resp.content
    assert b"Follow-ups Due" not in resp.content
    assert b"Weekly Application Target" not in resp.content
    assert b"breakdown-track" in resp.content


def test_dashboard_breakdown_bars_scale_to_total_applications(client, tmp_db):
    create_application(_app_data(status="applied", location="Bangalore", work_mode="remote"))
    create_application(_app_data(status="rejected", location="Hyderabad", work_mode="hybrid"))

    resp = client.get("/")

    assert resp.status_code == 200
    assert b"width: 50.0%" in resp.content


def test_applications_list_renders(client):
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert b"Applications" in resp.content


def test_applications_list_has_location_and_sort_controls(client):
    resp = client.get("/applications?sort=company_asc")
    assert resp.status_code == 200
    assert b"Location" in resp.content
    assert b"Company A-Z" in resp.content
    assert b"Search company, role, or location" in resp.content
    assert b"Bulk edit" in resp.content
    assert b"Select all applications" in resp.content
    assert b"Latest applied / status / oldest updated" in resp.content
    assert b"data-bulk-select hidden" in resp.content


def test_static_assets_are_cache_busted(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"app.css?v=20260801-5" in resp.content
    assert b"app.js?v=20260801-5" in resp.content


def test_application_dropdowns_render_color_codes(client):
    resp = client.get("/applications/new")
    assert resp.status_code == 200
    assert b'data-color-kind="status"' in resp.content
    assert b'class="status-option status-closed"' in resp.content
    assert b'class="source-option source-upwork"' in resp.content
    assert b'class="mode-option mode-freelance"' in resp.content


def test_bulk_update_route_updates_selected_fields(client, tmp_db):
    first = create_application(_app_data(company="BulkOne"))
    second = create_application(_app_data(company="BulkTwo"))
    response = client.post(
        "/applications/bulk-update",
        data={
            "application_ids": [str(first), str(second)],
            "status": "closed",
            "source": "upwork",
            "work_mode": "freelance",
        },
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/applications"


def test_application_list_only_shows_view_for_job_posting(client, tmp_db):
    with_url = create_application(_app_data(company="WithUrl", jd_url="https://example.com/job"))
    without_url = create_application(_app_data(company="WithoutUrl", jd_url=None))
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert f'href="https://example.com/job"' in resp.text
    assert f'data-view-url="/applications/{with_url}"' in resp.text
    assert f'data-view-url="/applications/{without_url}"' in resp.text


def test_application_form_renders(client):
    resp = client.get("/applications/new")
    assert resp.status_code == 200
    assert b"Add Application" in resp.content


def test_application_detail_renders_without_editing(client, tmp_db):
    app_id = create_application(
        _app_data(
            company="DetailCo",
            role_title="Platform Engineer",
            jd_url="https://example.com/jobs/detail",
        )
    )
    resp = client.get(f"/applications/{app_id}")
    assert resp.status_code == 200
    assert b"DetailCo" in resp.content
    assert b"Platform Engineer" in resp.content
    assert b"Duplicate as new" in resp.content
    assert b">Open job posting<" not in resp.content
    assert b'aria-label="Open job posting"' in resp.content


def test_application_list_uses_row_view_trigger(client, tmp_db):
    app_id = create_application(_app_data(company="RowCo", role_title="Row Engineer"))
    resp = client.get("/applications")
    assert resp.status_code == 200
    assert f'data-view-url="/applications/{app_id}"' in resp.text
    assert f'href="/applications/{app_id}"><' not in resp.text
    assert f'action="/applications/{app_id}/delete"' in resp.text


def test_application_delete_route_removes_row(client, tmp_db):
    app_id = create_application(_app_data(company="DeleteCo", role_title="Delete Engineer"))
    resp = client.post(f"/applications/{app_id}/delete")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/applications"

    detail = client.get(f"/applications/{app_id}")
    assert detail.status_code == 404


def test_application_detail_missing_returns_404(client):
    resp = client.get("/applications/99999")
    assert resp.status_code == 404


def test_followups_renders(client):
    resp = client.get("/followups")
    assert resp.status_code == 200


def test_csv_export_headers(client):
    resp = client.get("/export.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    reader = csv.DictReader(StringIO(resp.text))
    assert set(reader.fieldnames) >= {"id", "company", "role_title", "status"}


def test_csv_export_seeded_row(client, tmp_db):
    create_application(_app_data(company="ExportCo", role_title="Lead"))
    resp = client.get("/export.csv")
    assert resp.status_code == 200
    reader = csv.DictReader(StringIO(resp.text))
    rows = list(reader)
    assert any(r["company"] == "ExportCo" and r["role_title"] == "Lead" for r in rows)


def test_csv_export_escapes_formula_prefixes(client, tmp_db):
    create_application(_app_data(company="=cmd|'/c calc'!A0", role_title="Dev"))
    resp = client.get("/export.csv")
    reader = csv.DictReader(StringIO(resp.text))
    rows = list(reader)
    assert any(r["company"] == "\t=cmd|'/c calc'!A0" for r in rows)


def _post_form(**overrides):
    base = {
        "company": "PostCo",
        "role_title": "Engineer",
        "location": "",
        "work_mode": "remote",
        "source": "linkedin",
        "jd_url": "",
        "salary_min": "",
        "salary_max": "",
        "status": "saved",
        "resume_version": "",
        "applied_date": "",
        "follow_up_date": "",
        "notes": "",
    }
    return {**base, **overrides}


def test_create_application_redirects_to_edit(client):
    resp = client.post("/applications/new", data=_post_form())
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/applications/")
    assert not resp.headers["location"].endswith("/edit")


def test_create_application_validation_error(client):
    resp = client.post("/applications/new", data=_post_form(company=""))
    assert resp.status_code == 400
    assert b"Company is required." in resp.content


def test_create_application_invalid_date(client):
    resp = client.post("/applications/new", data=_post_form(applied_date="not-a-date"))
    assert resp.status_code == 400
    assert b"Applied date must be YYYY-MM-DD." in resp.content


def test_create_application_salary_min_exceeds_max(client):
    resp = client.post(
        "/applications/new", data=_post_form(salary_min="200000", salary_max="100000")
    )
    assert resp.status_code == 400
    assert b"Minimum salary must not exceed maximum salary." in resp.content


def test_create_application_duplicate_warns_then_confirms(client):
    resp1 = client.post("/applications/new", data=_post_form())
    assert resp1.status_code == 303

    resp2 = client.post("/applications/new", data=_post_form())
    assert resp2.status_code == 200
    assert b"possible duplicate" in resp2.content

    resp3 = client.post(
        "/applications/new", data=_post_form(duplicate_confirmed="1")
    )
    assert resp3.status_code == 303


def test_edit_application_updates_and_redirects(client):
    app_id = create_application(
        {
            "company": "EditCo",
            "role_title": "Dev",
            "location": None,
            "work_mode": "remote",
            "source": "linkedin",
            "jd_url": None,
            "salary_min": None,
            "salary_max": None,
            "status": "saved",
            "resume_version": None,
            "applied_date": None,
            "follow_up_date": None,
            "notes": None,
        }
    )
    resp = client.post(
        f"/applications/{app_id}/edit",
        data=_post_form(company="EditCo", status="applied"),
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/applications/{app_id}"

    edit_resp = client.get(f"/applications/{app_id}/edit")
    assert b"applied" in edit_resp.content


def test_edit_application_validation_error(client):
    app_id = create_application(
        {
            "company": "EditCo2",
            "role_title": "Dev",
            "location": None,
            "work_mode": "remote",
            "source": "linkedin",
            "jd_url": None,
            "salary_min": None,
            "salary_max": None,
            "status": "saved",
            "resume_version": None,
            "applied_date": None,
            "follow_up_date": None,
            "notes": None,
        }
    )
    resp = client.post(
        f"/applications/{app_id}/edit", data=_post_form(company="")
    )
    assert resp.status_code == 400
    assert b"Company is required." in resp.content


def test_edit_missing_application_returns_404(client):
    resp = client.get("/applications/99999/edit")
    assert resp.status_code == 404

    resp2 = client.post("/applications/99999/edit", data=_post_form())
    assert resp2.status_code == 404
