from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.queries import due_followups
from app.web import templates


router = APIRouter()


@router.get("/followups", response_class=HTMLResponse)
def followups(request: Request):
    return templates.TemplateResponse(
        request,
        "followups.html",
        {"applications": due_followups()},
    )
