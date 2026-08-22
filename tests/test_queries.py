from datetime import date

from app.queries import (
    create_application,
    bulk_update_application_fields,
    create_application_event,
    create_resume,
    delete_resume,
    due_followups,
    get_application,
    infer_source_from_url,
    import_applications_csv,
    import_applications_json,
    list_application_events,
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

    events = list_application_events(app_id)
    assert len(events) == 1
    assert events[0]["event_type"] == "created"


def test_create_application_logs_applied_event(tmp_db):
    app_id = create_application(
        _app_data(status="applied", applied_date="2026-08-01", notes="Applied online")
    )
    events = list_application_events(app_id)
    assert events[0]["event_type"] == "applied"
    assert events[0]["occurred_at"] == "2026-08-01"
    assert events[0]["note"] == "Applied online"


def test_update_application(tmp_db):
    app_id = create_application(_app_data())
    update_application(app_id, {"status": "applied", "notes": "Updated"})
    result = get_application(app_id)
    assert result["status"] == "applied"
    assert result["notes"] == "Updated"
    assert result["company"] == "Acme"

    events = list_application_events(app_id)
    assert [event["event_type"] for event in events][:2] == [
        "note_added",
        "status_changed",
    ]
    assert events[1]["metadata"] == {
        "from_status": "saved",
        "to_status": "applied",
    }


def test_update_application_logs_follow_up_and_resume_changes(tmp_db):
    app_id = create_application(_app_data())
    update_application(
        app_id,
        {"follow_up_date": "2026-08-20", "resume_version": "backend-2026"},
    )
    events = list_application_events(app_id)
    event_types = [event["event_type"] for event in events]
    assert "follow_up_scheduled" in event_types
    assert "resume_sent" in event_types


def test_create_application_event_validates_application_and_type(tmp_db):
    app_id = create_application(_app_data())
    event_id = create_application_event(app_id, "reply_received", note="Recruiter replied")
    assert event_id >= 1
    assert list_application_events(app_id)[0]["note"] == "Recruiter replied"

    try:
        create_application_event(app_id, "bad_type")
    except ValueError as exc:
        assert "Event type is invalid" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid event type")


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


def test_infer_source_from_url():
    assert infer_source_from_url("https://www.linkedin.com/jobs/view/1") == "linkedin"
    assert infer_source_from_url("https://jobs.lever.co/acme/123") == "company_portal"
    assert infer_source_from_url("https://careers.example.com/jobs/123") == "company_site"
    assert infer_source_from_url(None) is None


def test_import_applications_csv_creates_and_updates(tmp_db):
    app_id = create_application(_app_data(company="ImportCo", role_title="Old", status="saved"))
    summary = import_applications_csv(
        "\n".join(
            [
                "id,company,role_title,status,jd_url,source,work_mode,notes",
                f"{app_id},ImportCo,Old,applied,https://linkedin.com/jobs/1,other,remote,Updated",
                ",NewCo,Engineer,applied,https://jobs.lever.co/new/1,other,hybrid,Imported",
            ]
        )
    )

    assert summary["created"] == 1
    assert summary["updated"] == 1
    assert summary["skipped"] == 0
    updated = get_application(app_id)
    assert updated["status"] == "applied"
    assert updated["source"] == "linkedin"
    assert updated["notes"] == "Updated"

    rows = list_applications(search="NewCo")
    assert len(rows) == 1
    assert rows[0]["source"] == "company_portal"


def test_import_applications_csv_skips_invalid_rows(tmp_db):
    summary = import_applications_csv("company,role_title,status\n,Engineer,applied\n")
    assert summary["created"] == 0
    assert summary["updated"] == 0
    assert summary["skipped"] == 1
    assert "Company is required" in summary["errors"][0]


def test_import_applications_json_handles_linkedin_scraper_shape(tmp_db):
    summary = import_applications_json(
        """
        {
            "job_id": "4409004132",
            "title": "AI Data EngineerMultiBank Group",
            "company": null,
            "location": "Bengaluru",
            "status": "No longer accepting applications",
            "timestamp": "Applied 3mo ago",
            "job_url": "https://www.linkedin.com/jobs/view/4409004132/",
            "scraped_at": "2026-08-15T22:46:35.675Z"
        }
        """
    )

    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert summary["skipped"] == 0
    rows = list_applications(search="MultiBank")
    assert len(rows) == 1
    assert rows[0]["company"] == "MultiBank Group"
    assert rows[0]["role_title"] == "AI Data Engineer"
    assert rows[0]["location"] == "Bengaluru"
    assert rows[0]["status"] == "applied"
    assert rows[0]["source"] == "linkedin"
    assert "No longer accepting applications" in rows[0]["notes"]


def test_import_applications_json_accepts_arrays(tmp_db):
    summary = import_applications_json(
        """
        [
            {
                "title": "Backend Engineer - ArrayCo",
                "company": null,
                "job_url": "https://jobs.ashbyhq.com/array/1",
                "timestamp": "Applied today"
            }
        ]
        """
    )
    assert summary["created"] == 1
    row = list_applications(search="ArrayCo")[0]
    assert row["company"] == "ArrayCo"
    assert row["source"] == "company_portal"


def test_import_applications_json_handles_new_linkedin_structure(tmp_db):
    summary = import_applications_json(
        """
        {
            "job_id": "4416993718",
            "title": "AI Data Engineer",
            "company": "Influur",
            "location": "Greater Delhi Area",
            "work_type": "Remote",
            "status": "Closed",
            "applied_date": "2026-06-15",
            "job_url": "https://www.linkedin.com/jobs/view/4416993718/",
            "scraped_at": "2026-08-15T22:53:22.525Z"
        }
        """
    )

    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert summary["skipped"] == 0
    row = list_applications(search="Influur")[0]
    assert row["company"] == "Influur"
    assert row["role_title"] == "AI Data Engineer"
    assert row["location"] == "Greater Delhi Area"
    assert row["work_mode"] == "remote"
    assert row["status"] == "applied"
    assert row["applied_date"] == "2026-06-15"
    assert row["source"] == "linkedin"
    assert "Original status: Closed" in row["notes"]


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
