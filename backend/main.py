"""FastAPI app wiring: CORS, the health check, and the three routers. Nothing else lives here.

FROZEN (`STAGES.md` § FROZEN files). This file is app wiring and router registration only - no
business logic, no endpoint bodies. A new endpoint goes in the router that owns its resource
(`routes/reports.py`, `routes/review.py`, `routes/analytics.py`), never here.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import os
from pathlib import Path
from huggingface_hub import snapshot_download

# Auto-download model weights if missing locally
_WEIGHTS_DIR = Path(__file__).parent / "model_weights"
_HF_REPO = os.environ.get("HF_MODEL_REPO", "swayamohapatra/sentinel-sif")

if not (_WEIGHTS_DIR / "sif_classifier" / "model.safetensors").exists():
    print(f"Model weights not found locally. Auto-downloading from Hugging Face: {_HF_REPO}...")
    snapshot_download(repo_id=_HF_REPO, local_dir=str(_WEIGHTS_DIR))

from routes import analytics, reports, review, sites

load_dotenv()

app = FastAPI(title="SentinelSIF API")


def _scrub_unencodable(value):
    """Replace characters that cannot be encoded as UTF-8, recursively, leaving all else alone.

    Only lone surrogates (U+D800-U+DFFF) are unencodable in practice, and they become `?`. Every
    legitimate character is untouched - verified on Devanagari and on astral-plane emoji, both of
    which encode fine and so pass through unchanged.
    """
    if isinstance(value, str):
        return value.encode("utf-8", "replace").decode("utf-8")
    if isinstance(value, dict):
        return {_scrub_unencodable(key): _scrub_unencodable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_unencodable(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return FastAPI's ordinary 422 body, but scrubbed so serializing it cannot crash.

    WHY THIS EXISTS. FastAPI's default handler echoes the rejected input back in the error body.
    When that input contains a lone surrogate - legal in JSON as `\\udXXX`, produced by the
    server's own parser, and impossible for a client to send any other way - `JSONResponse.render`
    dies on `.encode("utf-8")` INSIDE the error handler. The validation itself worked correctly;
    reporting it was what failed, and the result was a raw `HTTP 500 Internal Server Error` with a
    `text/plain` body. `PRD.md` § Edge cases forbids both the crash and the raw 500. Observed
    against the running API and traced to
    `starlette/responses.py:201` before being fixed here (`AUDIT.md` 2026-08-26).

    IT IS FIXED HERE RATHER THAN IN `schemas.py` because a lone surrogate never reaches a field
    validator - Pydantic rejects it while parsing the string, so a validator could not see it. And
    it is registered app-wide rather than on the ingest route because every endpoint that echoes
    user input into a 422 has the same failure; one handler covers all of them.

    The 422 status, the `detail` key and its `{loc, msg, type}` entries are unchanged, so
    `frontend/lib/api_client.ts` needs no change and keeps reading the same shape.
    """
    return JSONResponse(status_code=422,
                        content={"detail": _scrub_unencodable(jsonable_encoder(exc.errors()))})

# The browser calls this API directly from the Next.js app, so the dev origin must be allowed.
# Read from the environment rather than hardcoded: the deployed frontend has a different origin,
# and a wildcard would leave the service-role-backed API open to any page on the internet.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(reports.router)
app.include_router(review.router)
app.include_router(analytics.router)
app.include_router(sites.router)


@app.get("/health")
def health():
    return {"status": "ok"}
