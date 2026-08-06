"""Shared manifest writer for the dev demo seeds.

The demo seeds delete and recreate their rows on every run, so every seeded
id is fresh. Anything that wants to drive the seeded dataset (the Playwright
live-stack suite, the screenshot harness) therefore cannot hardcode ids. A
hardcoded id silently points at a course that no longer exists, and a test
asserting on workspace chrome will happily pass against it.

Both seed scripts merge their ids into one JSON manifest that the e2e suite
reads. Merging (rather than overwriting) keeps `seed_demo.py`'s course ids
alive when `seed_demo_content.py` runs afterwards.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# backend/seed_manifest.py -> repo root -> frontend/e2e/.seed-manifest.json
MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "frontend" / "e2e" / ".seed-manifest.json"
)


def write_manifest(values: dict[str, Any]) -> None:
    """Merge `values` into the on-disk manifest, creating it if absent."""
    existing: dict[str, Any] = {}
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    merged = {**existing, **values}
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"  manifest: {MANIFEST_PATH}")
