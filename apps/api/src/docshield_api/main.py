"""Initial FastAPI application for DocsShield."""

from fastapi import FastAPI

app = FastAPI(
    title="DocsShield API",
    description="Document security inspection API — early development scaffold.",
    version="0.1.0",
)


@app.get("/health", tags=["operations"])
async def health_check() -> dict[str, str]:
    """Return the API process health status."""
    return {"status": "ok", "service": "docshield-api", "version": "0.1.0"}
