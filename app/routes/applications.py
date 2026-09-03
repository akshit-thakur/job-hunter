from dataclasses import dataclass
from datetime import date
from pathlib import Path
from shutil import rmtree
from uuid import uuid4
from urllib.parse import urlencode

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import UPLOADS_DIR
from app.models import (
    APPLICATION_EVENT_TYPES,
    APPLICATION_FIELDS,
    SOURCES,
    STATUSES,
    WORK_MODES,
)
from app.queries import (
    create_application_event,
    create_application,
    create_application_image,
    create_duplicate_application,
    delete_application,
    delete_application_image,
    bulk_update_application_fields,
    duplicate_application_template,
    duplicate_last_url,
    find_duplicate_candidate,
    get_application,
    get_application_image,
    import_applications_csv,
    import_applications_json,
    latest_application,
    list_application_events,
    list_application_images,
    list_applications,
    normalize_application_form,
    update_application,
)
from app.web import templates


router = APIRouter()

MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class PreparedImage:
    original_filename: str
    content: bytes
    content_type: str
    extension: str

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
    }


async def _save_application_images(
    application_id: int,
    images: list[UploadFile],
) -> int:
    return _save_prepared_application_images(
        application_id,
        await _prepare_application_images(images),
    )


async def _prepare_application_images(images: list[UploadFile]) -> list[PreparedImage]:
    prepared = []
    if not images:
        return prepared

    for image in images:
        if not image.filename:
            continue

        content = await image.read()
        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Images must be 10 MB or smaller.")

        detected = _detect_image_type(content)
        if detected is None:
            raise HTTPException(status_code=400, detail="Upload valid PNG, JPG, GIF, or WebP images.")

        content_type, extension = detected
        prepared.append(
            PreparedImage(
                original_filename=image.filename,
                content=content,
                content_type=content_type,
                extension=extension,
            )
        )

    return prepared


def _detect_image_type(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def _save_prepared_application_images(
    application_id: int,
    images: list[PreparedImage],
) -> int:
    saved_count = 0
    if not images:
        return saved_count

    image_dir = UPLOADS_DIR / "application_images" / str(application_id)
    image_dir.mkdir(parents=True, exist_ok=True)

    for image in images:
        stored_name = f"{uuid4().hex}{image.extension}"
        relative_path = Path("application_images") / str(application_id) / stored_name
        destination = image_dir / stored_name
        destination.write_bytes(image.content)
        try:
            create_application_image(
                application_id,
                original_filename=image.original_filename,
                stored_path=relative_path.as_posix(),
                content_type=image.content_type,
                size_bytes=len(image.content),
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        saved_count += 1
    return saved_count


@router.get("/applications", response_class=HTMLResponse)
def applications_list(
    request: Request,
    q: str = "",
    status: str = "",
    source: str = "",
    work_mode: str = "",
    sort: str = "applied_status_updated",
    imported_created: int | None = None,
    imported_updated: int | None = None,
    imported_skipped: int | None = None,
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
            import_summary=(
                {
                    "created": imported_created or 0,
                    "updated": imported_updated or 0,
                    "skipped": imported_skipped or 0,
                }
                if imported_created is not None
                or imported_updated is not None
                or imported_skipped is not None
                else None
            ),
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


@router.post("/applications/import")
async def import_applications_route(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload a CSV or JSON file.")
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
        if file.filename.lower().endswith(".csv"):
            summary = import_applications_csv(text)
        elif file.filename.lower().endswith(".json"):
            summary = import_applications_json(text)
        else:
            raise HTTPException(status_code=400, detail="Upload a CSV or JSON file.")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Import file must be UTF-8 encoded.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    params = urlencode(
        {
            "imported_created": summary["created"],
            "imported_updated": summary["updated"],
            "imported_skipped": summary["skipped"],
        }
    )
    return RedirectResponse(url=f"/applications?{params}", status_code=303)


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
    rmtree(UPLOADS_DIR / "application_images" / str(application_id), ignore_errors=True)
    return RedirectResponse(url="/applications", status_code=303)


@router.post("/applications/new")
async def create_application_route(request: Request):
    form = await request.form()
    raw = {field: str(form.get(field, "")) for field in FORM_FIELDS}
    prepared_images = await _prepare_application_images(form.getlist("images"))
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
    try:
        _save_prepared_application_images(application_id, prepared_images)
    except Exception:
        delete_application(application_id)
        rmtree(UPLOADS_DIR / "application_images" / str(application_id), ignore_errors=True)
        raise
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
        {
            "application": application,
            "events": list_application_events(application_id),
            "images": list_application_images(application_id),
            "event_types": APPLICATION_EVENT_TYPES,
        },
    )


@router.post("/applications/{application_id}/images")
async def upload_application_images(
    application_id: int,
    images: list[UploadFile] = File(...),
):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    if not images:
        raise HTTPException(status_code=400, detail="Choose at least one image.")

    saved_count = await _save_application_images(application_id, images)
    if saved_count == 0:
        raise HTTPException(status_code=400, detail="Choose at least one image.")

    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/images/{image_id}/delete")
def delete_application_image_route(application_id: int, image_id: int):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    image = get_application_image(image_id)
    if not image or image["application_id"] != application_id:
        raise HTTPException(status_code=404, detail="Image not found")

    deleted = delete_application_image(image_id)
    stored_path = UPLOADS_DIR / deleted["stored_path"]
    try:
        stored_path.unlink()
    except FileNotFoundError:
        pass
    create_application_event(
        application_id,
        "note_added",
        note=f"Deleted image: {deleted['original_filename']}",
    )
    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/events")
async def create_application_event_route(request: Request, application_id: int):
    application = get_application(application_id)
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    form = await request.form()
    event_type = str(form.get("event_type", "")).strip()
    note = str(form.get("note", "")).strip() or None
    next_follow_up_date = str(form.get("next_follow_up_date", "")).strip() or None

    if event_type not in APPLICATION_EVENT_TYPES:
        raise HTTPException(status_code=400, detail="Event type is invalid.")

    if event_type in {"rejected", "withdrawn"}:
        update_application(application_id, {"status": event_type})
        if note:
            create_application_event(application_id, "note_added", note=note)
    elif event_type == "offer_received":
        update_application(application_id, {"status": "offer"})
        if note:
            create_application_event(application_id, "note_added", note=note)
    else:
        create_application_event(application_id, event_type, note=note)

    if next_follow_up_date:
        update_application(application_id, {"follow_up_date": next_follow_up_date})
    elif event_type == "follow_up_sent" and application.get("follow_up_date"):
        update_application(application_id, {"follow_up_date": None})

    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/edit")
async def update_application_route(request: Request, application_id: int):
    existing = get_application(application_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Application not found")
    form = await request.form()
    raw = {field: str(form.get(field, "")) for field in FORM_FIELDS}
    prepared_images = await _prepare_application_images(form.getlist("images"))
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
    _save_prepared_application_images(application_id, prepared_images)
    return RedirectResponse(url=f"/applications/{application_id}", status_code=303)
