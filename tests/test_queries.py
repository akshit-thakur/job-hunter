from datetime import date

from app.queries import (
    create_application,
    bulk_update_application_fields,
    create_resume,
    delete_resume,
    due_followups,
    get_application,
    list_applications,
    update_application,
    update_resume,
    dashboard_metrics,
)


def _app_data(**overrides):
    base = {
        "company": "Acme",
        "role_title": "Engineer",
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


def test_create_and_get_application(tmp_db):
    app_id = create_application(_app_data(company="TestCo", role_title="Dev"))
    result = get_application(app_id)
    assert result["company"] == "TestCo"
    assert result["role_title"] == "Dev"
    assert result["status"] == "saved"
    assert result["created_at"] is not None
    assert result["updated_at"] is not None


def test_update_application(tmp_db):
    app_id = create_application(_app_data())
    update_application(app_id, {"status": "applied", "notes": "Updated"})
    result = get_application(app_id)
    assert result["status"] == "applied"
    assert result["notes"] == "Updated"
    assert result["company"] == "Acme"


def test_update_missing_application_raises(tmp_db):
    try:
        update_application(99999, {"status": "applied"})
    except ValueError as exc:
        assert "Application 99999" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing application")


def test_update_application_rejects_unknown_fields(tmp_db):
    app_id = create_application(_app_data())
    try:
        update_application(app_id, {"status = 'offer' --": "applied"})
    except ValueError as exc:
        assert "Unsupported application fields" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported application field")


def test_bulk_update_changes_only_status_source_and_work_mode(tmp_db):
    first = create_application(_app_data(company="First", notes="Keep this"))
    second = create_application(_app_data(company="Second", notes="Keep that"))
    bulk_update_application_fields(
        [first, second],
        {"status": "closed", "source": "upwork", "work_mode": "freelance"},
    )
    for application_id, notes in ((first, "Keep this"), (second, "Keep that")):
        application = get_application(application_id)
        assert application["status"] == "closed"
        assert application["source"] == "upwork"
        assert application["work_mode"] == "freelance"
        assert application["notes"] == notes


def test_update_and_delete_missing_resume_raise(tmp_db):
    try:
        update_resume(99999, {"name": "missing", "notes": None, "is_default": False})
    except ValueError as exc:
        assert "Resume 99999" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing resume update")

    resume_id = create_resume({"name": "temp", "notes": None, "is_default": False})
    delete_resume(resume_id)

    try:
        delete_resume(resume_id)
    except ValueError as exc:
        assert f"Resume {resume_id}" in str(exc)
    else:
        raise AssertionError("Expected ValueError for missing resume delete")


def test_list_applications_status_filter(tmp_db):
    create_application(_app_data(status="saved"))
    create_application(_app_data(status="applied"))
    create_application(_app_data(status="rejected"))

    applied = list_applications(status="applied")
    assert len(applied) == 1
    assert applied[0]["status"] == "applied"


def test_list_applications_source_filter(tmp_db):
    create_application(_app_data(source="linkedin"))
    create_application(_app_data(source="job_board"))
    create_application(_app_data(source="referral"))

    job_board = list_applications(source="job_board")
    assert len(job_board) == 1
    assert job_board[0]["source"] == "job_board"


def test_list_applications_work_mode_filter(tmp_db):
    create_application(_app_data(work_mode="remote"))
    create_application(_app_data(work_mode="onsite"))

    remote = list_applications(work_mode="remote")
    assert len(remote) == 1 and remote[0]["work_mode"] == "remote"


def test_list_applications_searches_location_and_sorts(tmp_db):
    create_application(_app_data(company="Zulu", location="Bangalore"))
    create_application(_app_data(company="Alpha", location="Remote"))

    remote = list_applications(search="Bangalore")
    assert len(remote) == 1 and remote[0]["company"] == "Zulu"

    alphabetical = list_applications(sort="company_asc")
    assert [row["company"] for row in alphabetical] == ["Alpha", "Zulu"]


def test_dashboard_metrics_submitted_this_week(tmp_db):
    today = date.today().isoformat()
    create_application(_app_data(applied_date=today, status="applied"))
    create_application(_app_data(applied_date=today, status="applied"))
    m = dashboard_metrics()
    assert m["submitted_this_week"] == 2
    assert m["total_applications"] == 2


def test_dashboard_metrics_count_closed_applications(tmp_db):
    create_application(_app_data(status="closed"))
    create_application(_app_data(status="rejected"))
    create_application(_app_data(status="applied"))
    metrics = dashboard_metrics()
    assert metrics["closed_applications"] == 1


def test_default_application_sort_is_applied_status_then_oldest_updated(tmp_db):
    create_application(_app_data(company="Later", applied_date="2026-08-02", status="saved"))
    create_application(_app_data(company="Earlier", applied_date="2026-08-01", status="applied"))
    rows = list_applications()
    assert [row["company"] for row in rows] == ["Later", "Earlier"]

    invalid_sort = list_applications(sort="not-a-sort")
    assert [row["company"] for row in invalid_sort] == ["Later", "Earlier"]


def test_dashboard_metrics_include_location_and_work_mode_breakdowns(tmp_db):
    create_application(_app_data(location="Bangalore", work_mode="hybrid"))
    create_application(_app_data(location="Bangalore", work_mode="remote"))
    metrics = dashboard_metrics()

    assert {row["label"]: row["count"] for row in metrics["location_breakdown"]} == {
        "Bangalore": 2
    }
    assert {row["label"]: row["count"] for row in metrics["work_mode_breakdown"]} == {
        "hybrid": 1,
        "remote": 1,
    }


def test_dashboard_metrics_exclude_freelance_and_unknown_values(tmp_db):
    create_application(_app_data(company="Tracked", location="Bangalore", work_mode="remote"))
    create_application(_app_data(company="Freelance", location="Remote", work_mode="freelance"))
    create_application(_app_data(company="Unknown", location=None, work_mode="unknown"))
    metrics = dashboard_metrics()

    assert metrics["total_applications"] == 2
    assert metrics["active_applications"] == 2
    assert metrics["location_breakdown"] == [{"label": "Bangalore", "count": 1}]
    assert metrics["work_mode_breakdown"] == [{"label": "remote", "count": 1}]


def test_application_options_include_closed_freelance_and_new_sources(tmp_db):
    from app.models import SOURCES, STATUSES, WORK_MODES

    assert "closed" in STATUSES
    assert "freelance" in WORK_MODES
    assert {"naukri", "indeed", "company_portal", "upwork", "network"}.issubset(SOURCES)


def test_due_followups(tmp_db):
    past = "2020-01-01"
    future = "2099-12-31"
    create_application(_app_data(follow_up_date=past, status="applied"))
    create_application(_app_data(follow_up_date=future, status="applied"))
    create_application(_app_data(follow_up_date=past, status="rejected"))

    today = date.today().isoformat()
    due = due_followups(today)
    assert len(due) == 1
    assert due[0]["follow_up_date"] == past
