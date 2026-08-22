"""JSON API for native and browser quick-add clients."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.models import STATUSES
from app.queries import create_application, normalize_application_form, stats_for_api


router = APIRouter(tags=["api"])


class ApplicationCreateRequest(BaseModel):
    """Compact payload used by the menu-bar quick-log form."""

    company: str = Field(..., min_length=1)
    role: str = Field(..., min_length=1)
    url: str | None = None
    status: str = "applied"
    notes: str | None = None
    source: str | None = None
    work_mode: str | None = None
    location: str | None = None
    resume_version: str | None = None
    follow_up_date: str | None = None

    @field_validator("company", "role", mode="before")
    @classmethod
    def strip_required(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator(
        "url",
        "notes",
        "source",
        "work_mode",
        "location",
        "resume_version",
        "follow_up_date",
        mode="before",
    )
    @classmethod
    def strip_optional(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            return text or None
        return value

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> Any:
        if value is None or value == "":
            return "applied"
        if isinstance(value, str):
            return value.strip()
        return value


class ApplicationCreateResponse(BaseModel):
    id: int
    company: str
    role: str
    url: str | None
    status: str
    notes: str | None
    source: str
    work_mode: str
    location: str | None
    resume_version: str | None
    follow_up_date: str | None


class StatsResponse(BaseModel):
    applied: int
    interviewing: int
    active: int
    total: int
    submitted_this_week: int
    weekly_target: int
    followups_due: int


@router.get("/stats", response_model=StatsResponse)
def get_stats() -> StatsResponse:
    return StatsResponse(**stats_for_api())


@router.post("/applications", response_model=ApplicationCreateResponse, status_code=201)
def post_application(body: ApplicationCreateRequest) -> ApplicationCreateResponse:
    if body.status not in STATUSES:
        raise HTTPException(status_code=422, detail="Status is invalid.")

    form: dict[str, Any] = {
        "company": body.company,
        "role_title": body.role,
        "jd_url": body.url,
        "status": body.status,
        "notes": body.notes,
        "work_mode": body.work_mode or "unknown",
        "source": body.source or "other",
        "location": body.location,
        "salary_min": None,
        "salary_max": None,
        "resume_version": body.resume_version,
        "applied_date": date.today().isoformat() if body.status != "saved" else None,
        "follow_up_date": body.follow_up_date,
    }
    data, errors = normalize_application_form(form)
    if errors:
        raise HTTPException(status_code=422, detail=errors)

    application_id = create_application(data)
    return ApplicationCreateResponse(
        id=application_id,
        company=data["company"],
        role=data["role_title"],
        url=data["jd_url"],
        status=data["status"],
        notes=data["notes"],
        source=data["source"],
        work_mode=data["work_mode"],
        location=data["location"],
        resume_version=data["resume_version"],
        follow_up_date=data["follow_up_date"],
    )
