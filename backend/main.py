"""FastAPI app wiring: CORS, the health check, and the three routers. Nothing else lives here.

FROZEN (`STAGES.md` § FROZEN files). This file is app wiring and router registration only - no
business logic, no endpoint bodies. A new endpoint goes in the router that owns its resource
(`routes/reports.py`, `routes/review.py`, `routes/analytics.py`), never here.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import analytics, reports, review, sites

load_dotenv()

app = FastAPI(title="SentinelSIF API")

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
