from __future__ import annotations

import json
import csv
import re
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Any
from urllib.parse import urlparse

from app.config import weekly_target as _weekly_target
from app.db import get_connection
from app.models import (
    APPLICATION_EVENT_TYPES,
    APPLICATION_FIELDS,
    CLOSED_STATUSES,
    SOURCES,
    STATUSES,
    WORK_MODES,
)


IST = timezone(timedelta(hours=5, minutes=30))

SOURCE_HOST_PATTERNS = {
    "linkedin": ("linkedin.com",),
    "indeed": ("indeed.com",),
    "naukri": ("naukri.com",),
    "job_board": (
        "wellfound.com",
        "angel.co",
        "instahyre.com",
        "cutshort.io",
        "foundit.in",
        "monster.com",
        "dice.com",
        "hired.com",
    ),
    "company_portal": (
        "greenhouse.io",
        "lever.co",
        "ashbyhq.com",
        "workdayjobs.com",
        "myworkdayjobs.com",
        "icims.com",
        "smartrecruiters.com",
        "bamboohr.com",
        "workable.com",
        "jobvite.com",
        "successfactors.com",
        "oraclecloud.com",
        "taleo.net",
        "recruitee.com",
    ),
}

IMPORT_FIELD_ALIASES = {
    "title": "role_title",
    "role": "role_title",
    "url": "jd_url",
    "job_url": "jd_url",
    "job_posting_url": "jd_url",
    "mode": "work_mode",
    "jd": "job_description",
    "description": "job_description",
    "followup_date": "follow_up_date",
}

COMPANY_SUFFIX_PATTERN = re.compile(
    r"^(.+?[a-z0-9])([A-Z][A-Za-z0-9&.,' -]*(?:Group|Inc|LLC|Ltd|Limited|Corporation|Corp|Company|Technologies|Systems|Solutions|Bank)\b.*)$"
)


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


def clean_import_text(value: Any) -> str | None:
    text = clean_text(value)
    if text and text.startswith("\t"):
        text = text[1:]
    return text or None


def split_import_title(title: str | None) -> tuple[str | None, str | None]:
    text = clean_import_text(title)
    if not text:
        return None, None
    for separator in (" | ", " - ", " at ", " @ "):
        if separator in text:
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) >= 2:
                return parts[0], parts[-1]
    match = COMPANY_SUFFIX_PATTERN.match(text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text, None


def infer_source_from_url(url: str | None) -> str | None:
    text = clean_text(url)
    if not text:
        return None
    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    for source, patterns in SOURCE_HOST_PATTERNS.items():
        for pattern in patterns:
            normalized = pattern.lower()
            if host == normalized or host.endswith(f".{normalized}"):
                return source
    return "company_site"


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
    jd_url = clean_text(form.get("jd_url"))
    source = clean_text(form.get("source")) or "other"
    inferred_source = infer_source_from_url(jd_url)
    if source == "other" and inferred_source:
        source = inferred_source
    data = {
        "company": clean_text(form.get("company")),
        "role_title": clean_text(form.get("role_title")),
        "location": clean_text(form.get("location")),
        "work_mode": clean_text(form.get("work_mode")) or "unknown",
        "source": source,
        "jd_url": jd_url,
        "salary_min": parse_float(form.get("salary_min"), "Minimum salary", errors),
        "salary_max": parse_float(form.get("salary_max"), "Maximum salary", errors),
        "status": clean_text(form.get("status")) or "saved",
        "job_description": clean_text(form.get("job_description")),
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


def _event_label(event_type: str) -> str:
    return event_type.replace("_", " ").title()


def _create_application_event(
    conn,
    application_id: int,
    event_type: str,
    *,
    note: str | None = None,
    occurred_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    if event_type not in APPLICATION_EVENT_TYPES:
        raise ValueError("Event type is invalid.")
    now = ist_now_iso()
    cursor = conn.execute(
        """
        insert into application_events
            (application_id, event_type, occurred_at, note, metadata_json, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (
            application_id,
            event_type,
            occurred_at or now,
            clean_text(note),
            json.dumps(metadata, sort_keys=True) if metadata else None,
            now,
        ),
    )
    return int(cursor.lastrowid)


def create_application_event(
    application_id: int,
    event_type: str,
    note: str | None = None,
    occurred_at: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    with closing(get_connection()) as conn:
        if not conn.execute(
            "select 1 from applications where id = ?", (application_id,)
        ).fetchone():
            raise ValueError(f"Application {application_id} does not exist.")
        event_id = _create_application_event(
            conn,
            application_id,
            event_type,
            note=note,
            occurred_at=occurred_at,
            metadata=metadata,
        )
        conn.commit()
        return event_id


def list_application_events(application_id: int) -> list[dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            select * from application_events
            where application_id = ?
            order by occurred_at desc, id desc
            """,
            (application_id,),
        ).fetchall()
    events = []
    for row in rows:
        event = dict(row)
        event["label"] = _event_label(event["event_type"])
        event["metadata"] = json.loads(event["metadata_json"]) if event["metadata_json"] else {}
        events.append(event)
    return events


def list_application_images(application_id: int) -> list[dict[str, Any]]:
    with closing(get_connection()) as conn:
        rows = conn.execute(
            """
            select * from application_images
            where application_id = ?
            order by created_at desc, id desc
            """,
            (application_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_application_image(
    application_id: int,
    *,
    original_filename: str,
    stored_path: str,
    content_type: str,
    size_bytes: int,
    caption: str | None = None,
) -> int:
    now = ist_now_iso()
    with closing(get_connection()) as conn:
        if not conn.execute(
            "select 1 from applications where id = ?", (application_id,)
        ).fetchone():
            raise ValueError(f"Application {application_id} does not exist.")
        cursor = conn.execute(
            """
            insert into application_images
                (application_id, original_filename, stored_path, content_type, size_bytes, caption, created_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                application_id,
                clean_text(original_filename) or "job-posting-image",
                stored_path,
                content_type,
                size_bytes,
                clean_text(caption),
                now,
            ),
        )
        _create_application_event(
            conn,
            application_id,
            "note_added",
            note=f"Added image: {clean_text(original_filename) or 'job-posting-image'}",
        )
        conn.commit()
        return int(cursor.lastrowid)


def get_application_image(image_id: int) -> dict[str, Any] | None:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select * from application_images where id = ?", (image_id,)
        ).fetchone()
    return dict(row) if row else None


def delete_application_image(image_id: int) -> dict[str, Any]:
    with closing(get_connection()) as conn:
        row = conn.execute(
            "select * from application_images where id = ?", (image_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Application image {image_id} does not exist.")
        conn.execute("delete from application_images where id = ?", (image_id,))
        conn.commit()
    return dict(row)


def _initial_event_type(data: dict[str, Any]) -> str:
    status = data.get("status")
    if status == "applied":
        return "applied"
    if status == "rejected":
        return "rejected"
    if status == "withdrawn":
        return "withdrawn"
    if status == "offer":
        return "offer_received"
    return "created"


def _status_event_type(new_status: str) -> str:
    if new_status == "rejected":
        return "rejected"
    if new_status == "withdrawn":
        return "withdrawn"
    if new_status == "offer":
        return "offer_received"
    return "status_changed"


def _log_application_changes(
    conn,
    application_id: int,
    existing: dict[str, Any],
    values: dict[str, Any],
) -> None:
    if "status" in values and values["status"] != existing.get("status"):
        _create_application_event(
            conn,
            application_id,
            _status_event_type(values["status"]),
            metadata={
                "from_status": existing.get("status"),
                "to_status": values["status"],
            },
        )
    if (
        "follow_up_date" in values
        and values["follow_up_date"]
        and values["follow_up_date"] != existing.get("follow_up_date")
    ):
        _create_application_event(
            conn,
            application_id,
            "follow_up_scheduled",
            metadata={
                "old_follow_up_date": existing.get("follow_up_date"),
                "new_follow_up_date": values["follow_up_date"],
            },
        )
    if "notes" in values and values["notes"] and values["notes"] != existing.get("notes"):
        _create_application_event(conn, application_id, "note_added", note=values["notes"])


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
        application_id = int(cursor.lastrowid)
        _create_application_event(
            conn,
            application_id,
            _initial_event_type(data),
            note=data.get("notes"),
            occurred_at=data.get("applied_date") or now,
        )
        conn.commit()
        return application_id


def _import_row_to_form(row: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    form = {
        field: existing.get(field) if existing else None
        for field in APPLICATION_FIELDS
        if field not in ("id", "created_at", "updated_at")
    }
    for key, value in row.items():
        if key is None:
            continue
        normalized_key = key.strip().lower()
        field = IMPORT_FIELD_ALIASES.get(normalized_key, normalized_key)
        if field in form:
            form[field] = clean_import_text(value)
    return form


def _normalize_json_import_status(item: dict[str, Any]) -> str | None:
    if clean_import_text(item.get("applied_date")):
        return "applied"
    timestamp = clean_import_text(item.get("timestamp"))
    raw_status = clean_import_text(item.get("status"))
    if timestamp and timestamp.lower().startswith("applied"):
        return "applied"
    if not raw_status:
        return None
    status = raw_status.lower()
    if "reject" in status:
        return "rejected"
    if "withdraw" in status:
        return "withdrawn"
    if "offer" in status:
        return "offer"
    if "interview" in status:
        return "hr_screen"
    if "no longer accepting" in status or "closed" in status:
        return "closed"
    if "applied" in status:
        return "applied"
    return None


def _normalize_json_work_mode(item: dict[str, Any]) -> str | None:
    raw_work_type = clean_import_text(item.get("work_type") or item.get("work_mode"))
    if not raw_work_type:
        return None
    work_type = raw_work_type.lower()
    for mode in WORK_MODES:
        if mode in work_type:
            return mode
    return None


def _json_item_to_import_row(item: dict[str, Any]) -> dict[str, Any]:
    role_title, company_from_title = split_import_title(item.get("title"))
    company = clean_import_text(item.get("company")) or company_from_title
    job_url = clean_import_text(item.get("job_url") or item.get("url"))
    status = _normalize_json_import_status(item)
    note_parts = []
    for label, key in (
        ("Job ID", "job_id"),
        ("Original status", "status"),
        ("Timestamp", "timestamp"),
        ("Scraped at", "scraped_at"),
    ):
        value = clean_import_text(item.get(key))
        if value:
            note_parts.append(f"{label}: {value}")
    return {
        "company": company,
        "role_title": role_title,
        "location": clean_import_text(item.get("location")),
        "work_mode": _normalize_json_work_mode(item),
        "status": status,
        "applied_date": clean_import_text(item.get("applied_date")),
        "jd_url": job_url,
        "source": clean_import_text(item.get("source")) or "other",
        "job_description": clean_import_text(
            item.get("job_description") or item.get("description")
        ),
        "notes": "\n".join(note_parts) or None,
    }


def _find_import_target(conn, row: dict[str, Any]) -> dict[str, Any] | None:
    raw_id = clean_import_text(row.get("id"))
    if raw_id:
        try:
            application_id = int(raw_id)
        except ValueError:
            application_id = 0
        if application_id:
            existing = conn.execute(
                "select * from applications where id = ?", (application_id,)
            ).fetchone()
            if existing:
                return dict(existing)

    company = clean_import_text(row.get("company"))
    role = clean_import_text(row.get("role_title") or row.get("role"))
    if company and role:
        existing = conn.execute(
            "select * from applications where lower(company)=lower(?) and lower(role_title)=lower(?) limit 1",
            (company, role),
        ).fetchone()
        if existing:
            return dict(existing)
    return None


def import_applications_csv(content: str) -> dict[str, Any]:
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames:
        raise ValueError("CSV must include a header row.")

    summary = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
    with closing(get_connection()) as conn:
        for index, row in enumerate(reader, start=2):
            if not any(clean_import_text(value) for value in row.values()):
                summary["skipped"] += 1
                continue

            existing = _find_import_target(conn, row)
            form = _import_row_to_form(row, existing)
            data, errors = normalize_application_form(form)
            if errors:
                summary["skipped"] += 1
                summary["errors"].append(f"Row {index}: {' '.join(errors)}")
                continue

            if existing:
                try:
                    update_application(existing["id"], data)
                except ValueError as exc:
                    summary["skipped"] += 1
                    summary["errors"].append(f"Row {index}: {exc}")
                    continue
                summary["updated"] += 1
            else:
                create_application(data)
                summary["created"] += 1
    return summary


def import_applications_json(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON is invalid: {exc.msg}") from exc
    if isinstance(payload, dict):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        raise ValueError("JSON import must be an object or an array of objects.")

    output = StringIO()
    fieldnames = [
        "company",
        "role_title",
        "location",
        "work_mode",
        "status",
        "applied_date",
        "jd_url",
        "source",
        "job_description",
        "notes",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"JSON item {index} must be an object.")
        writer.writerow(_json_item_to_import_row(item))
    return import_applications_csv(output.getvalue())


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
        existing = conn.execute(
            "select * from applications where id = ?", (application_id,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Application {application_id} does not exist.")
        cursor = conn.execute(
            f"update applications set {assignments} where id = ?",
            [values[column] for column in columns] + [application_id],
        )
        try:
            ensure_one_row(cursor, "Application", application_id)
        except ValueError:
            conn.rollback()
            raise
        _log_application_changes(conn, application_id, dict(existing), values)
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
    if column not in {"status", "source", "location", "work_mode"}:
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
