from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.config import weekly_target as _weekly_target
from app.db import get_connection
from app.models import APPLICATION_FIELDS, CLOSED_STATUSES, SOURCES, STATUSES, WORK_MODES


IST = timezone(timedelta(hours=5, minutes=30))


def ist_now_iso() -> str:
    return datetime.now(IST).replace(microsecond=0).isoformat()


def week_bounds(today: date) -> tuple[date, date]:
    week_start = date.fromordinal(today.toordinal() - today.weekday())
    return week_start, date.fromordinal(week_start.toordinal() + 6)


def ensure_one_row(cursor, entity: str, entity_id: int) -> None:
    if cursor.rowcount != 1:
        raise ValueError(f"{entity} {entity_id} does not exist.")


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_date(value: Any, field: str, errors: list[str]) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        date.fromisoformat(text)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD.")
        return None
    return text


def parse_float(value: Any, field: str, errors: list[str]) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        errors.append(f"{field} must be numeric.")
        return None


def normalize_application_form(form: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    data = {
        "company": clean_text(form.get("company")),
        "role_title": clean_text(form.get("role_title")),
        "location": clean_text(form.get("location")),
        "work_mode": clean_text(form.get("work_mode")) or "unknown",
        "source": clean_text(form.get("source")) or "other",
        "jd_url": clean_text(form.get("jd_url")),
        "salary_min": parse_float(form.get("salary_min"), "Minimum salary", errors),
        "salary_max": parse_float(form.get("salary_max"), "Maximum salary", errors),
        "status": clean_text(form.get("status")) or "saved",
        "resume_version": clean_text(form.get("resume_version")),
        "applied_date": parse_date(form.get("applied_date"), "Applied date", errors),
        "follow_up_date": parse_date(form.get("follow_up_date"), "Follow-up date", errors),
        "notes": clean_text(form.get("notes")),
    }

    if not data["company"]:
        errors.append("Company is required.")
    if not data["role_title"]:
        errors.append("Role title is required.")
    if data["status"] not in STATUSES:
        errors.append("Status is invalid.")
    if data["work_mode"] not in WORK_MODES:
        errors.append("Work mode is invalid.")
    if data["source"] not in SOURCES:
        errors.append("Source is invalid.")
    if (
        data["salary_min"] is not None
        and data["salary_max"] is not None
        and data["salary_min"] > data["salary_max"]
    ):
        errors.append("Minimum salary must not exceed maximum salary.")

    return data, errors


def create_application(data: dict[str, Any]) -> int:
    now = ist_now_iso()
    values = {**data, "created_at": now, "updated_at": now}
    columns = [field for field in APPLICATION_FIELDS if field != "id"]
    placeholders = ", ".join("?" for _ in columns)
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            f"insert into applications ({', '.join(columns)}) values ({placeholders})",
            [values.get(column) for column in columns],
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_application(application_id: int, data: dict[str, Any]) -> None:
    allowed_columns = {
        field for field in APPLICATION_FIELDS if field not in ("id", "created_at")
    }
    unexpected_columns = set(data) - allowed_columns
    if unexpected_columns:
        raise ValueError(
            f"Unsupported application fields: {', '.join(sorted(unexpected_columns))}."
        )
    values = {**data, "updated_at": ist_now_iso()}
    columns = [field for field in values.keys() if field != "created_at"]
    assignments = ", ".join(f"{column} = ?" for column in columns)
    with closing(get_connection()) as conn:
        cursor = conn.execute(
            f"update applications set {assignments} where id = ?",
            [values[column] for column in columns] + [application_id],
        )
        try:
            ensure_one_row(cursor, "Application", application_id)
        except ValueError:
            conn.rollback()
            raise
        conn.commit()


def delete_application(application_id: int) -> None:
    with closing(get_connection()) as conn:
        cursor = conn.execute("delete from applications where id = ?", (application_id,))
        try:
            ensure_one_row(cursor, "Application", application_id)
        except ValueError:
            conn.rollback()
            raise
        conn.commit()


def bulk_update_application_fields(application_ids: list[int], data: dict[str, str]) -> None:
    allowed_fields = {"status", "source", "work_mode"}
    unexpected_fields = set(data) - allowed_fields
    if unexpected_fields:
        raise ValueError(
            f"Unsupported bulk fields: {', '.join(sorted(unexpected_fields))}."
        )
    updates = {field: value for field, value in data.items() if value}
    if not updates:
        raise ValueError("Choose at least one field to update.")
    if not application_ids:
        raise ValueError("Select at least one application.")
    if "status" in updates and updates["status"] not in STATUSES:
        raise ValueError("Status is invalid.")
    if "source" in updates and updates["source"] not in SOURCES:
        raise ValueError("Source is invalid.")
    if "work_mode" in updates and updates["work_mode"] not in WORK_MODES:
        raise ValueError("Work mode is invalid.")

    ids = list(dict.fromkeys(application_ids))
    assignments = ", ".join(f"{field} = ?" for field in updates)
    values = [updates[field] for field in updates]
    with closing(get_connection()) as conn:
        existing_ids = {
            row[0]
            for row in conn.execute(
                f"select id from applications where id in ({', '.join('?' for _ in ids)})",
                ids,
            ).fetchall()
        }
        missing_ids = set(ids) - existing_ids
        if missing_ids:
            raise ValueError(f"Application {min(missing_ids)} does not exist.")
        for application_id in ids:
            cursor = conn.execute(
                f"update applications set {assignments}, updated_at = ? where id = ?",
                [*values, ist_now_iso(), application_id],
            )
            ensure_one_row(cursor, "Application", application_id)
        conn.commit()


def find_duplicate_candidate(company: str, role_title: str) -> dict[str, Any] | None:
    """Return the first existing application with a matching company+role, or None."""
    if not company or not role_title:
        return None
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select * from applications where lower(company)=lower(?) and lower(role_title)=lower(?) limit 1",
            (company, role_title),
        ).fetchone()
    return dict(row) if row else None


def get_application(application_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select * from applications where id = ?", (application_id,)
        ).fetchone()
    return dict(row) if row else None


def list_applications(
    search: str | None = None,
    status: str | None = None,
    source: str | None = None,
    work_mode: str | None = None,
    sort: str = "applied_status_updated",
) -> list[dict[str, Any]]:
    sort_columns = {
        "applied_status_updated": "applied_date desc, status collate nocase asc, updated_at asc, id desc",
        "updated_desc": "updated_at desc, id desc",
        "applied_desc": "applied_date desc, updated_at desc, id desc",
        "company_asc": "company collate nocase asc, role_title collate nocase asc, id desc",
        "location_asc": "location collate nocase asc, company collate nocase asc, id desc",
        "status_asc": "status collate nocase asc, updated_at desc, id desc",
    }
    order_by = sort_columns.get(sort, sort_columns["applied_status_updated"])
    clauses: list[str] = []
    params: list[Any] = []
    if search:
        clauses.append("(company like ? or role_title like ? or location like ?)")
        token = f"%{search}%"
        params.extend([token, token, token])
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if work_mode:
        clauses.append("work_mode = ?")
        params.append(work_mode)
    where = f"where {' and '.join(clauses)}" if clauses else ""
    with closing(get_connection()) as conn:
        rows = conn.execute(
            f"select * from applications {where} order by {order_by}", params
        ).fetchall()
    return [dict(row) for row in rows]


def due_followups(today: str | None = None) -> list[dict[str, Any]]:
    today = today or date.today().isoformat()
    placeholders = ", ".join("?" for _ in CLOSED_STATUSES)
    with closing(get_connection()) as conn:
        rows = conn.execute(
            f"""
            select * from applications
            where follow_up_date is not null
              and follow_up_date <= ?
              and status not in ({placeholders})
            order by follow_up_date asc, updated_at desc
            """,
            [today, *CLOSED_STATUSES],
        ).fetchall()
    return [dict(row) for row in rows]


def _count_value(
    conn,
    column: str,
    *,
    exclude_freelance: bool = False,
    exclude_unknown: bool = False,
) -> list[dict[str, Any]]:
    if column not in {"status", "source", "resume_version", "location", "work_mode"}:
        raise ValueError("Unsupported breakdown column.")
    label = f"coalesce(nullif({column}, ''), 'unset')"
    clauses = []
    if exclude_freelance:
        clauses.append("coalesce(work_mode, '') != 'freelance'")
    if exclude_unknown:
        clauses.append(f"nullif({column}, '') is not null and lower({column}) != 'unknown'")
    where = f"where {' and '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"select {label} as label, count(*) as count from applications {where} group by label order by count desc, label"
    ).fetchall()
    return [dict(row) for row in rows]


def count_value(
    column: str,
    *,
    exclude_freelance: bool = False,
    exclude_unknown: bool = False,
) -> list[dict[str, Any]]:
    with closing(get_connection()) as conn:
        return _count_value(
            conn,
            column,
            exclude_freelance=exclude_freelance,
            exclude_unknown=exclude_unknown,
        )


def dashboard_metrics(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    week_start, week_end = week_bounds(today)
    closed_placeholders = ", ".join("?" for _ in CLOSED_STATUSES)
    with closing(get_connection()) as conn:
        headline = conn.execute(
            f"""
            select
                count(*) as total,
                coalesce(sum(case when applied_date between ? and ? then 1 else 0 end), 0) as submitted,
                coalesce(sum(case when status not in ({closed_placeholders}) then 1 else 0 end), 0) as active,
                coalesce(sum(case when status = 'rejected' then 1 else 0 end), 0) as rejected,
                coalesce(sum(case when status = 'closed' then 1 else 0 end), 0) as closed
            from applications
            where coalesce(work_mode, '') != 'freelance'
            """,
            [week_start.isoformat(), week_end.isoformat(), *CLOSED_STATUSES],
        ).fetchone()
        breakdowns = {
            "status_breakdown": _count_value(
                conn, "status", exclude_freelance=True, exclude_unknown=True
            ),
            "source_breakdown": _count_value(
                conn, "source", exclude_freelance=True, exclude_unknown=True
            ),
            "location_breakdown": _count_value(
                conn, "location", exclude_freelance=True, exclude_unknown=True
            ),
            "work_mode_breakdown": _count_value(
                conn, "work_mode", exclude_freelance=True, exclude_unknown=True
            ),
        }
    target = _weekly_target()
    return {
        "submitted_this_week": headline["submitted"],
        "weekly_target": target,
        "remaining_this_week": max(target - headline["submitted"], 0),
        "total_applications": headline["total"],
        "active_applications": headline["active"],
        "rejected_applications": headline["rejected"],
        "closed_applications": headline["closed"],
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        **breakdowns,
    }


def all_applications() -> list[dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "select * from applications order by updated_at desc, id desc"
        ).fetchall()
    return [dict(row) for row in rows]


INTERVIEWING_STATUSES = ("hr_screen", "tech_round", "final_round")


def stats_for_api() -> dict[str, Any]:
    """Compact counters for native and browser quick-add clients."""
    week_start, week_end = week_bounds(date.today())
    interviewing_placeholders = ", ".join("?" for _ in INTERVIEWING_STATUSES)
    closed_placeholders = ", ".join("?" for _ in CLOSED_STATUSES)
    with closing(get_connection()) as conn:
        stats = conn.execute(
            f"""
            select
                count(*) as total,
                coalesce(sum(case when status != 'saved' then 1 else 0 end), 0) as applied,
                coalesce(sum(case when status in ({interviewing_placeholders}) then 1 else 0 end), 0) as interviewing,
                coalesce(sum(case when status not in ({closed_placeholders}) then 1 else 0 end), 0) as active,
                coalesce(sum(case when applied_date between ? and ? then 1 else 0 end), 0) as submitted,
                coalesce(sum(case when follow_up_date is not null and follow_up_date <= ? and status not in ({closed_placeholders}) then 1 else 0 end), 0) as followups_due
            from applications
            where coalesce(work_mode, '') != 'freelance'
            """,
            [
                *INTERVIEWING_STATUSES,
                *CLOSED_STATUSES,
                week_start.isoformat(),
                week_end.isoformat(),
                date.today().isoformat(),
                *CLOSED_STATUSES,
            ],
        ).fetchone()
    return {
        "applied": stats["applied"],
        "interviewing": stats["interviewing"],
        "active": stats["active"],
        "total": stats["total"],
        "submitted_this_week": stats["submitted"],
        # Kept for compatibility with already-installed menu-bar clients.
        "weekly_target": _weekly_target(),
        "followups_due": stats["followups_due"],
    }


def duplicate_application_template(source_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return (form values, duplicate_from metadata) for a new application."""
    source = get_application(source_id)
    if not source:
        return None
    application = {
        field: source.get(field)
        for field in APPLICATION_FIELDS
        if field not in ("id", "created_at", "updated_at")
    }
    application["company"] = ""
    application["jd_url"] = ""
    duplicate_from = {
        "id": source["id"],
        "company": source["company"],
        "role_title": source["role_title"],
    }
    return application, duplicate_from


def create_duplicate_application(source_id: int) -> int | None:
    duplicated = duplicate_application_template(source_id)
    if duplicated is None:
        return None
    application, _duplicate_from = duplicated
    return create_application(application)


def latest_application() -> dict[str, Any] | None:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select * from applications order by updated_at desc, id desc limit 1"
        ).fetchone()
    return dict(row) if row else None


def duplicate_last_url() -> str | None:
    latest = latest_application()
    if not latest:
        return None
    return f"/applications/{latest['id']}/duplicate"


def list_resume_names() -> list[str]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "select name from resumes order by is_default desc, name collate nocase"
        ).fetchall()
    return [row[0] for row in rows]


def list_resumes() -> list[dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            "select * from resumes order by is_default desc, name collate nocase"
        ).fetchall()
    return [dict(row) for row in rows]


def get_resume(resume_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as conn:
        row = conn.execute("select * from resumes where id = ?", (resume_id,)).fetchone()
    return dict(row) if row else None


def default_resume_name() -> str | None:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select name from resumes where is_default = 1 order by id limit 1"
        ).fetchone()
    return row[0] if row else None


def normalize_resume_form(form: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    name = clean_text(form.get("name"))
    notes = clean_text(form.get("notes"))
    is_default = str(form.get("is_default", "")).lower() in {"1", "true", "on", "yes"}
    if not name:
        errors.append("Resume name is required.")
    return {"name": name, "notes": notes, "is_default": is_default}, errors


def create_resume(data: dict[str, Any]) -> int:
    now = ist_now_iso()
    with closing(get_connection()) as conn:
        if data["is_default"]:
            conn.execute("update resumes set is_default = 0")
        cursor = conn.execute(
            """
            insert into resumes (name, notes, is_default, created_at, updated_at)
            values (?, ?, ?, ?, ?)
            """,
            (data["name"], data["notes"], int(data["is_default"]), now, now),
        )
        conn.commit()
        return int(cursor.lastrowid)


def update_resume(resume_id: int, data: dict[str, Any]) -> None:
    now = ist_now_iso()
    with closing(get_connection()) as conn:
        if data["is_default"]:
            conn.execute("update resumes set is_default = 0")
        cursor = conn.execute(
            """
            update resumes
            set name = ?, notes = ?, is_default = ?, updated_at = ?
            where id = ?
            """,
            (data["name"], data["notes"], int(data["is_default"]), now, resume_id),
        )
        try:
            ensure_one_row(cursor, "Resume", resume_id)
        except ValueError:
            conn.rollback()
            raise
        conn.commit()


def delete_resume(resume_id: int) -> None:
    with closing(get_connection()) as conn:
        cursor = conn.execute("delete from resumes where id = ?", (resume_id,))
        try:
            ensure_one_row(cursor, "Resume", resume_id)
        except ValueError:
            conn.rollback()
            raise
        conn.commit()


def resume_usage_count(name: str) -> int:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select count(*) from applications where resume_version = ?", (name,)
        ).fetchone()
    return int(row[0])
