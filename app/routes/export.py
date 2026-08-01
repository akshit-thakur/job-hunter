from datetime import date

from fastapi import APIRouter
from fastapi.responses import Response

from app.csv_export import applications_csv


router = APIRouter()


@router.get("/export.csv")
def export_csv():
    filename = f"job_applications_{date.today().strftime('%Y%m%d')}.csv"
    return Response(
        content=applications_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
