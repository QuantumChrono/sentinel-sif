"""Shared fixtures. Kept to exactly two: a fake DB and a client wired to it, because every
test in this suite needs both and nothing more.
"""

import pytest
from fastapi.testclient import TestClient

import routes.reports as reports_module
import routes.review as review_module
from main import app

from fake_supabase import FakeSupabase


@pytest.fixture
def fake_db(monkeypatch):
    """Replace `supabase` in every route module that imported it by name
    (`from database import supabase`). `monkeypatch` restores the real reference after each
    test automatically, so tests cannot leak state into one another.
    """
    fake = FakeSupabase()
    monkeypatch.setattr(reports_module, "supabase", fake)
    monkeypatch.setattr(review_module, "supabase", fake)
    return fake


@pytest.fixture
def client(fake_db):  # noqa: ARG001 - depended on for its side effect (the patch), not its value
    return TestClient(app)
