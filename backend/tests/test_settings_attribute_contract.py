"""Every ``settings.<name>`` an LLM path reads must exist on ``Settings``.

``app/services/failures.py`` opens by describing the failure that made typed
error codes a release gate: an instructor was shown

    AttributeError: 'Settings' object has no attribute 'llm_primary_model'

That work stopped the string reaching the screen. It did not fix the attribute.
``Settings`` declares ``openrouter_primary_model``; six call sites still read
``settings.llm_primary_model``, so every one of them raises at runtime and gets
classified as ``analysis_unavailable`` — a typed, user-safe rendering of a
feature that has never once worked. Production bears this out: every syllabus
import ever recorded is ``failed``, the older ones with exactly that code.

The first test pins the syllabus path that instructors actually hit. The second
is the general guard: a typo'd settings attribute is invisible until the moment
a background job dies of it, so it is caught here instead.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from app.config import settings

APP_ROOT = pathlib.Path(__file__).resolve().parent.parent / "app"


def _settings_attributes_referenced() -> dict[str, list[str]]:
    """Map ``settings.<attr>`` -> the ``file:line`` sites that read it."""
    found: dict[str, list[str]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "settings"
            ):
                site = f"{path.relative_to(APP_ROOT.parent)}:{node.lineno}"
                found.setdefault(node.attr, []).append(site)
    return found


def test_no_code_reads_a_settings_attribute_that_does_not_exist():
    referenced = _settings_attributes_referenced()
    missing = {
        attr: sites
        for attr, sites in referenced.items()
        if not hasattr(settings, attr)
    }
    assert not missing, (
        "these settings attributes are read but not declared, so every call "
        "site raises AttributeError the moment it runs:\n"
        + "\n".join(
            f"  settings.{attr} -> {', '.join(sites)}"
            for attr, sites in sorted(missing.items())
        )
    )


@pytest.mark.asyncio
async def test_syllabus_extraction_uses_the_configured_model(monkeypatch):
    """The syllabus LLM call reaches the provider with a real model id.

    Deliberately does not patch ``_llm_extract`` (the rest of the syllabus
    suite does, which is why this defect survived): the whole point is to run
    the real settings access on the way to the client.
    """
    import app.services.syllabus as syllabus_module

    captured: dict[str, object] = {}

    class _FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class _Msg:
                content = '{"schema_version": "v1"}'

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    class _FakeClient:
        def __init__(self, **_kwargs):
            self.chat = type("_Chat", (), {"completions": _FakeCompletions()})()

    monkeypatch.setattr(syllabus_module, "AsyncOpenAI", _FakeClient)

    payload = await syllabus_module.parse_syllabus_text("Course X. Week 1: Intro")

    assert payload["schema_version"] == "v1"
    assert captured["model"] == settings.openrouter_primary_model
    assert captured["model"], "a blank model id would 400 at the provider"
