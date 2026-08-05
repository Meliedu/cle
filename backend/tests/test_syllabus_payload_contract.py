"""The extraction schema must accept what a real syllabus actually contains.

Production evidence (course d0311e9b, import 98dad610, 4 Aug 2026): a real
MGMT2130 syllabus parsed to 10,567 characters of clean text, and the whole
import was then thrown away by ``_SyllabusPayloadV1`` over five field errors:

    meetings.0.meeting_index: Input should be greater than or equal to 1
    assignments.{0,1,2,4}.due_at: Input should be a valid string (got None)

Both are contract defects on our side, not bad model output:

  * ``due_at`` was required, while the prompt says "Do not hallucinate dates".
    A syllabus routinely weights components it never dates ("Attendance and
    Participation, 15%"), so the model returned null, correctly, and the entire
    syllabus was discarded. ``apply_syllabus_payload`` already skips undated
    assignments, so nothing downstream needed the field to be mandatory.

  * ``meeting_index`` had to be >= 1, but nothing in the prompt said so while
    the neighbouring ``module_index`` is 0-based, so the model numbered from 0.

1-based meetings are the real product contract (the UI renders "Session
{meeting_index}" and the meetings API declares ``ge=1``), so the prompt now
states it. These tests additionally pin that a 0-based answer is renumbered
rather than discarded, references included: losing an instructor's whole
syllabus to an off-by-one is the failure this module exists to prevent.
"""

from __future__ import annotations

import pytest

from app.services.syllabus import parse_syllabus_text


def _payload(**overrides):
    base = {
        "course": {"name": "Business Ethics", "semester": "SPR 2026"},
        "modules": [],
        "meetings": [],
        "objectives": [],
        "assignments": [],
        "schema_version": "v1",
    }
    base.update(overrides)
    return base


async def _parse(monkeypatch, payload):
    import app.services.syllabus as syllabus_module

    async def _fake_extract(_raw):
        return payload

    monkeypatch.setattr(syllabus_module, "_llm_extract", _fake_extract)
    return await parse_syllabus_text("irrelevant")


@pytest.mark.asyncio
async def test_an_undated_graded_component_is_kept(monkeypatch):
    """The exact shape that discarded the MGMT2130 syllabus."""
    result = await _parse(
        monkeypatch,
        _payload(
            assignments=[
                {
                    "title": "Attendance and Participation",
                    "kind": "participation",
                    "due_at": None,
                    "weight": 0.15,
                },
                {
                    "title": "Final Report",
                    "kind": "essay",
                    "due_at": "2026-05-10T23:59:00",
                    "weight": 0.4,
                },
            ]
        ),
    )
    assert [a["title"] for a in result["assignments"]] == [
        "Attendance and Participation",
        "Final Report",
    ]
    assert result["assignments"][0]["due_at"] is None
    assert result["assignments"][1]["due_at"] == "2026-05-10T23:59:00"


@pytest.mark.asyncio
async def test_an_undated_session_is_kept(monkeypatch):
    """``scheduled_at`` is the same defect as ``due_at``, found in review.

    A schedule that reads "Week 3: Utilitarianism" with no calendar date is at
    least as common as an undated graded component, and the prompt forbids
    inventing one. ``apply_syllabus_payload`` already skips meetings without a
    usable date, so requiring it here could only ever discard the syllabus
    whole.
    """
    result = await _parse(
        monkeypatch,
        _payload(
            meetings=[
                {"meeting_index": 1, "title": "Intro", "scheduled_at": None},
                {"meeting_index": 2, "scheduled_at": "2026-02-12T11:00:00"},
            ]
        ),
    )
    assert [m["meeting_index"] for m in result["meetings"]] == [1, 2]
    assert result["meetings"][0]["scheduled_at"] is None
    assert result["meetings"][1]["scheduled_at"] == "2026-02-12T11:00:00"


@pytest.mark.asyncio
async def test_a_meeting_without_an_index_does_not_gain_a_null_one(monkeypatch):
    """Renumbering must not invent keys the model never sent.

    Injecting an explicit ``meeting_index: None`` turns "Field required" into
    "Input should be a valid integer" in ``tasks.error_message``, which
    misdirects whoever triages it.
    """
    import app.services.syllabus as syllabus_module

    payload = _payload(
        meetings=[
            {"meeting_index": 0, "scheduled_at": "2026-02-05T11:00:00"},
            {"title": "Unnumbered", "scheduled_at": "2026-02-12T11:00:00"},
        ]
    )
    shifted = syllabus_module._renumber_zero_based_meetings(payload)

    assert shifted["meetings"][0]["meeting_index"] == 1
    assert "meeting_index" not in shifted["meetings"][1]
    # The input is untouched: callers may still hold a reference to it.
    assert payload["meetings"][0]["meeting_index"] == 0


@pytest.mark.asyncio
async def test_zero_based_meetings_are_renumbered_not_discarded(monkeypatch):
    result = await _parse(
        monkeypatch,
        _payload(
            meetings=[
                {"meeting_index": 0, "scheduled_at": "2026-02-05T11:00:00"},
                {"meeting_index": 1, "scheduled_at": "2026-02-12T11:00:00"},
            ]
        ),
    )
    assert [m["meeting_index"] for m in result["meetings"]] == [1, 2]


@pytest.mark.asyncio
async def test_renumbering_carries_references_with_it(monkeypatch):
    """A shifted meeting must not leave its assignments pointing elsewhere."""
    result = await _parse(
        monkeypatch,
        _payload(
            meetings=[
                {"meeting_index": 0, "scheduled_at": "2026-02-05T11:00:00"},
                {"meeting_index": 1, "scheduled_at": "2026-02-12T11:00:00"},
            ],
            assignments=[
                {
                    "title": "Case memo",
                    "kind": "essay",
                    "due_at": "2026-02-12T23:59:00",
                    "meeting_index": 1,
                }
            ],
            objectives=[
                {"scope": "meeting", "scope_index": 0, "statement": "Frame a dilemma"},
                {"scope": "course", "scope_index": 0, "statement": "Course-wide aim"},
            ],
        ),
    )
    assert [m["meeting_index"] for m in result["meetings"]] == [1, 2]
    # The assignment pointed at the meeting the model called 1, now called 2.
    assert result["assignments"][0]["meeting_index"] == 2
    # Meeting-scoped objective follows the same renumbering...
    meeting_obj = next(o for o in result["objectives"] if o["scope"] == "meeting")
    assert meeting_obj["scope_index"] == 1
    # ...while a course-scoped index is not a meeting reference and must not move.
    course_obj = next(o for o in result["objectives"] if o["scope"] == "course")
    assert course_obj["scope_index"] == 0


@pytest.mark.asyncio
async def test_one_based_meetings_are_left_alone(monkeypatch):
    result = await _parse(
        monkeypatch,
        _payload(
            meetings=[
                {"meeting_index": 1, "scheduled_at": "2026-02-05T11:00:00"},
                {"meeting_index": 2, "scheduled_at": "2026-02-12T11:00:00"},
            ],
            assignments=[
                {
                    "title": "Case memo",
                    "kind": "essay",
                    "due_at": "2026-02-12T23:59:00",
                    "meeting_index": 2,
                }
            ],
        ),
    )
    assert [m["meeting_index"] for m in result["meetings"]] == [1, 2]
    assert result["assignments"][0]["meeting_index"] == 2


@pytest.mark.asyncio
async def test_the_prompt_states_both_index_bases_and_optional_dates():
    """The contract the model is asked to honour must be written down.

    Relaxing the schema without fixing the prompt would just move the
    ambiguity: the model would keep guessing the base, and every guess would
    need repairing after the fact.
    """
    from app.services.syllabus import _SYSTEM_PROMPT

    prompt = _SYSTEM_PROMPT.lower()
    assert "meeting_index" in prompt and "starts at 1" in prompt
    assert "order_index" in prompt and "starts at 0" in prompt
    assert "due_at" in prompt and "null" in prompt
