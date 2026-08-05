"""Every ``settings.<name>`` an LLM path reads must exist on ``Settings``.

``app/services/failures.py`` opens by describing the failure that made typed
error codes a release gate: an instructor was shown

    AttributeError: 'Settings' object has no attribute 'llm_primary_model'

That work stopped the string reaching the screen. It did not fix the attribute.
``Settings`` declares ``openrouter_primary_model``; six call sites still read
``settings.llm_primary_model``, so every one of them raises at runtime and gets
classified as ``analysis_unavailable``, a typed, user-safe rendering of a
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


def _binds_settings(node: ast.AST) -> bool:
    """Whether a function binds the name ``settings`` itself.

    Several modules take an unrelated ``settings`` parameter (a dict of report
    options, for instance). Those attribute reads say nothing about
    ``app.config.Settings``, so the walk must not treat them as references.
    """
    args = getattr(node, "args", None)
    if args is not None:
        names = [
            *getattr(args, "posonlyargs", []),
            *args.args,
            *args.kwonlyargs,
            *([args.vararg] if args.vararg else []),
            *([args.kwarg] if args.kwarg else []),
        ]
        if any(a.arg == "settings" for a in names):
            return True
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == "settings":
            if isinstance(child.ctx, (ast.Store, ast.Del)):
                return True
    return False


def _collect(node: ast.AST, path: pathlib.Path, found: dict[str, list[str]]) -> None:
    """Record ``settings.<attr>`` reads, skipping scopes that shadow the name."""
    for child in ast.iter_child_nodes(node):
        if isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ) and _binds_settings(child):
            continue
        if (
            isinstance(child, ast.Attribute)
            and isinstance(child.value, ast.Name)
            and child.value.id == "settings"
        ):
            site = f"{path.relative_to(APP_ROOT.parent)}:{child.lineno}"
            found.setdefault(child.attr, []).append(site)
        _collect(child, path, found)


def _settings_attributes_referenced() -> dict[str, list[str]]:
    """Map ``settings.<attr>`` -> the ``file:line`` sites that read it.

    Known blind spots, none of which occur today: ``getattr(settings, name)``
    with a computed name, an aliased import, and anything outside ``app/``
    (``scripts/`` is not scanned).
    """
    found: dict[str, list[str]] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        _collect(tree, path, found)
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


def test_the_walker_ignores_an_unrelated_local_named_settings():
    """Guard the guard: a shadowed name must not be reported as a config read.

    Without this, adding one field access to a function that takes its own
    ``settings`` parameter (``app/api/reports.py`` has one) fails the suite for
    a reason that has nothing to do with ``app.config``.
    """
    tree = ast.parse(
        "def render(settings):\n"
        "    return settings.definitely_not_a_config_field\n"
    )
    found: dict[str, list[str]] = {}
    _collect(tree, APP_ROOT / "fake.py", found)
    assert found == {}


def test_the_walker_still_sees_a_real_module_level_read():
    tree = ast.parse("from app.config import settings\nX = settings.database_url\n")
    found: dict[str, list[str]] = {}
    _collect(tree, APP_ROOT / "fake.py", found)
    assert "database_url" in found


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
