from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.models import APPLICATION_FIELDS, SOURCES, STATUSES, WORK_MODES
from app.queries import (
    create_application,
    create_duplicate_application,
    delete_application,
    bulk_update_application_fields,
    default_resume_name,
    duplicate_application_template,
    duplicate_last_url,
    find_duplicate_candidate,
    get_application,
    latest_application,
    list_applications,
    list_resume_names,
    normalize_application_form,
    update_application,
)
from app.web import templates


router = APIRouter()

FORM_FIELDS = tuple(
    field for field in APPLICATION_FIELDS if field not in ("id", "created_at", "updated_at")
)


def form_context(
    application=None,
    errors=None,
    mode="new",
    duplicate_warning=None,
    duplicate_from=None,
):
    latest = latest_application()
    return {
        "application": application or {},
        "errors": errors or [],
        "mode": mode,
        "statuses": STATUSES,
        "sources": SOURCES,
        "work_modes": WORK_MODES,
        "resume_names": list_resume_names(),
        "duplicate_warning": duplicate_warning,
        "duplicate_from": duplicate_from,
        "latest_application": latest,
        "duplicate_last_url": duplicate_last_url(),
        "today": date.today().isoformat(),
    }


def list_context(**extra):
    return {
        "duplicate_last_url": duplicate_last_url(),
        "latest_application": latest_application(),
        **extra,
    }


def _new_application_defaults() -> dict:
    today = date.today().isoformat()
    return {
        "status": "applied",
        "applied_date": today,
        "source": "other",
        "work_mode": "unknown",
        "resume_version": default_resume_name(),
    }


@router.get("/applications", response_class=HTMLResponse)
def applications_list(
    request: Request,
    q: str = "",
    status: str = "",
    source: str = "",
    work_mode: str = "",
    sort: str = "applied_status_updated",
    ):
    applications = list_applications(
        search=q.strip() or None,
        status=status or None,
        source=source or None,
        work_mode=work_mode or None,
        sort=sort,
    )
    return templates.TemplateResponse(
        request,
        "applications_list.html",
        list_context(
            applications=applications,
            filters={
                "q": q,
                "status": status,
                "source": source,
                "work_mode": work_mode,
                "sort": sort,
            },
            statuses=STATUSES,
            sources=SOURCES,
            work_modes=WORK_MODES,
        ),
    )


@router.post("/applications/bulk-update")
async def bulk_update_applications_route(request: Request):
    form = await request.form()
    try:
        application_ids = [int(value) for value in form.getlist("application_ids")]
        bulk_update_application_fields(
            application_ids,
            {
                "status": str(form.get("status", "")),
                "source": str(form.get("source", "")),
                "work_mode": str(form.get("work_mode", "")),
            },
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url="/applications", status_code=303)


@router.get("/applications/new", response_class=HTMLResponse)
def new_application(request: Request, from_id: int | None = None):
    duplicate_from = None
    application = _new_application_defaults()
    if from_id is not None:
        duplicated = duplicate_application_template(from_id)
        if duplicated is None:
            raise HTTPException(status_code=404, detail="Application not found")
        application, duplicate_from = duplicated
    return templates.TemplateResponse(
        request,
        "application_form.html",
        form_context(
            application=application,
            mode="new",
            duplicate_from=duplicate_from,
        ),
    )


@router.get("/applications/{application_id}/duplicate", response_class=HTMLResponse)
def duplicate_application(request: Request, application_id: int):
    duplicated = duplicate_application_template(application_id)
    if duplicated is None:
        raise HTTPException(status_code=404, detail="Application not found")
    application, duplicate_from = duplicated
    return templates.TemplateResponse(
        request,
        "application_form.html",
        form_context(application=application, mode="new", duplicate_from=duplicate_from),
    )


@router.post("/applications/{application_id}/duplicate")
def create_from_duplicate_route(application_id: int):
    duplicated_id = create_duplicate_application(application_id)
    if duplicated_id is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return RedirectResponse(url=f"/applications/{duplicated_id}/edit", status_code=303)


@router.post("/applications/{application_id}/delete")
def delete_application_route(application_id: int):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    delete_application(application_id)
    return RedirectResponse(url="/applications", status_code=303)


@router.post("/applications/new")
async def create_application_route(request: Request):
    form = await request.form()
    raw = {field: str(form.get(field, "")) for field in FORM_FIELDS}
    duplicate_confirmed = str(form.get("duplicate_confirmed", ""))
    data, errors = normalize_application_form(raw)
    if errors:
        return templates.TemplateResponse(
            request,
            "application_form.html",
            form_context(application={**raw, **data}, errors=errors, mode="new"),
            status_code=400,
        )
    if not duplicate_confirmed:
        duplicate = find_duplicate_candidate(data["company"], data["role_title"])
        if duplicate:
            return templates.TemplateResponse(
                request,
                "application_form.html",
                form_context(
                    application={**raw, **data},
                    mode="new",
                    duplicate_warning=duplicate,
                ),
            )
    application_id = create_application(data)
    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)


@router.get("/applications/{application_id}/edit", response_class=HTMLResponse)
def edit_application(request: Request, application_id: int):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return templates.TemplateResponse(
        request,
        "application_form.html",
        form_context(application=application, mode="edit"),
    )


@router.get("/applications/{application_id}", response_class=HTMLResponse)
def application_detail(request: Request, application_id: int):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return templates.TemplateResponse(
        request,
        "application_detail.html",
        {"application": application},
    )


@router.post("/applications/{application_id}/edit")
async def update_application_route(request: Request, application_id: int):
    existing = get_application(application_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Application not found")
    form = await request.form()
    raw = {field: str(form.get(field, "")) for field in FORM_FIELDS}
    data, errors = normalize_application_form(raw)
    if errors:
        return templates.TemplateResponse(
            request,
            "application_form.html",
            form_context(
                application={**existing, **raw, **data},
                errors=errors,
                mode="edit",
            ),
            status_code=400,
        )
    update_application(application_id, data)
    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)
