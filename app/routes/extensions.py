from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.config import ZEN_EXTENSION_DIR


router = APIRouter(tags=["extension"])

EXTENSION_FILES = (
    "manifest.json",
    "popup.html",
    "popup.css",
    "popup.js",
    "icon.svg",
)


@router.get("/extension/zen.zip", name="download_zen_extension")
def download_zen_extension() -> Response:
    missing = [name for name in EXTENSION_FILES if not (ZEN_EXTENSION_DIR / name).is_file()]
    if missing:
        raise HTTPException(status_code=503, detail="Extension package is unavailable.")

    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as bundle:
        for name in EXTENSION_FILES:
            bundle.write(ZEN_EXTENSION_DIR / name, arcname=name)

    return Response(
        content=archive.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="job-tracker-zen-extension.zip"',
            "Cache-Control": "no-store",
        },
    )
