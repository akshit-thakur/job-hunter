from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.queries import dashboard_metrics
from app.web import templates


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"metrics": dashboard_metrics()},
    )
