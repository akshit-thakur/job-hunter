from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.queries import (
    create_resume,
    delete_resume,
    get_resume,
    list_resumes,
    normalize_resume_form,
    resume_usage_count,
)
from app.web import templates


router = APIRouter()


@router.get("/resumes", response_class=HTMLResponse)
def resumes_list(request: Request):
    resumes = [
        {**resume, "usage_count": resume_usage_count(resume["name"])}
        for resume in list_resumes()
    ]
    return templates.TemplateResponse(
        request,
        "resumes.html",
        {"resumes": resumes, "draft": {}},
    )


@router.post("/resumes/new")
async def create_resume_route(request: Request):
    form = await request.form()
    data, errors = normalize_resume_form(dict(form))
    if errors:
        return templates.TemplateResponse(
            request,
            "resumes.html",
            {
                "resumes": [
                    {**resume, "usage_count": resume_usage_count(resume["name"])}
                    for resume in list_resumes()
                ],
                "errors": errors,
                "draft": data,
            },
            status_code=400,
        )
    create_resume(data)
    return RedirectResponse(url="/resumes", status_code=303)


@router.post("/resumes/{resume_id}/delete")
def delete_resume_route(resume_id: int):
    existing = get_resume(resume_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Resume not found")
    delete_resume(resume_id)
    return RedirectResponse(url="/resumes", status_code=303)
