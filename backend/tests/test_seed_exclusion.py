"""P7 H3 — seed/demo data must be excluded from production.

Spec §8 release hygiene: no seed/demo/test accounts in a production build or
runtime. Every seed entrypoint must FAIL CLOSED when the runtime environment is
production — it must refuse to run WITHOUT writing anything to the database.

The deployed backend image (``backend/Dockerfile``) copies the whole source
tree (``COPY . .`` with no ``.dockerignore``), so ``seed.py`` / ``seed_demo.py``
ARE present in the image. The real protection is therefore the runtime env-gate
inside each seed's entrypoint, which these tests pin. The frontend demo-auth
seed (``frontend/scripts/seed-auth.mjs``) is gated symmetrically on
``NODE_ENV=production``; we assert its guard statically.
"""

import asyncio
from pathlib import Path

import pytest

from app.config import settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def _db_tripwire(*args, **kwargs):
    """Stand-in for ``async_session_factory`` that PROVES the code path
    reached the database. If a production-gated seed ever calls this, the
    guard failed to fail-closed."""
    raise AssertionError(
        "seed reached the database — production guard did not fail closed"
    )


# --- Runtime fail-closed behaviour (the load-bearing protection) --------------


def test_seed_refuses_in_production(monkeypatch):
    import seed

    monkeypatch.setattr(settings, "environment", "production")
    # If the guard is missing, execution falls through to the DB and trips this.
    monkeypatch.setattr(seed, "async_session_factory", _db_tripwire)

    with pytest.raises(SystemExit):
        asyncio.run(seed.seed())


def test_seed_demo_refuses_in_production(monkeypatch):
    import seed_demo

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(seed_demo, "async_session_factory", _db_tripwire)

    with pytest.raises(SystemExit):
        asyncio.run(seed_demo.seed())


def test_seed_is_not_gated_outside_production(monkeypatch):
    """The guard must fire ONLY in production — a development run proceeds past
    the guard toward the DB (here intercepted by the tripwire)."""
    import seed

    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(seed, "async_session_factory", _db_tripwire)

    # Passing the guard means we reach the DB call → the tripwire fires.
    with pytest.raises(AssertionError):
        asyncio.run(seed.seed())


# --- Static guard presence (belt-and-suspenders across all seed entrypoints) --


def test_backend_seed_sources_have_production_guard():
    for name in ("seed.py", "seed_demo.py"):
        src = (BACKEND_DIR / name).read_text(encoding="utf-8")
        assert 'settings.environment == "production"' in src, (
            f"{name} is missing a production environment guard"
        )
        assert "SystemExit" in src, f"{name} guard must refuse via SystemExit"


def test_frontend_demo_seed_has_production_guard():
    src = (REPO_ROOT / "frontend" / "scripts" / "seed-auth.mjs").read_text(
        encoding="utf-8"
    )
    assert 'process.env.NODE_ENV === "production"' in src, (
        "seed-auth.mjs is missing a NODE_ENV=production guard"
    )
    assert "process.exit(1)" in src, (
        "seed-auth.mjs guard must exit non-zero in production"
    )
