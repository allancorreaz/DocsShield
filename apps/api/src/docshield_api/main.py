"""FastAPI application for the DocsShield inspection service."""

from fastapi import FastAPI, File, HTTPException, UploadFile, status

from docshield_api.pdf_inspector import PDFInspectionError, inspect_pdf

MAX_UPLOAD_BYTES = 20 * 1024 * 1024

app = FastAPI(
    title="DocsShield API",
    description="Document security inspection API — early development.",
    version="0.2.0",
)


@app.get("/health", tags=["operations"])
async def health_check() -> dict[str, str]:
    """Return the API process health status."""
    return {"status": "ok", "service": "docshield-api", "version": "0.2.0"}


@app.post("/v1/scans/pdf", tags=["scans"], status_code=status.HTTP_200_OK)
async def scan_pdf(file: UploadFile = File(...)) -> dict:
    """Inspect a PDF using the initial deterministic analyzer.

    This synchronous endpoint is for development only. Production deployments
    must move parsing to isolated workers with strict resource limits.
    """
    chunks: list[bytes] = []
    total_size = 0
    while chunk := await file.read(1024 * 1024):
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="The uploaded file exceeds the 20 MiB limit.",
            )
        chunks.append(chunk)

    content = b"".join(chunks)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    try:
        return inspect_pdf(content)
    except PDFInspectionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    finally:
        await file.close()
