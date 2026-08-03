"""Reader for the placement Administrator Pack.

The controlled artefact a proctor works from: the listening scripts, the answer
text and rationale behind each key, and the printed "No. / Key / Band / Skill /
Item ID" tables. Everything here is restricted and none of it may reach a
learner, which is why it is read from a different file than the item text.

The printed tables are parsed as well as the prose. They are a third
independent statement of the key -- alongside the workbook's ``Item Metadata``
and ``Key Matrix`` -- and ``extract_placement_bank`` requires all three to
agree before it will assemble an item.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Sequence

from scripts.pdf_layout import Line, group_paragraphs, read_lines, right_margin
from scripts.placement_sources import (
    ITEMS_PER_FORM,
    SPEAKER_TURN,
    ExtractError,
    assert_no_severed_page_break,
    clean,
    is_furniture,
)

ADMIN_HEADING = re.compile(r"^Q(\d{1,2})\s*·\s*(\S+)\s*·\s*legacy HSK(\d)$")
ADMIN_KEY = re.compile(r"^Key:\s*([A-F](?:-[A-F])*)\s*·\s*(.*?)(?:\s*\|\s*(.*))?$")
ADMIN_FORM = re.compile(
    r"^(?:CONTROLLED KEY\s*·\s*FORM ([A-E])|Form ([A-E]): answer key and scripts)$"
)
_ADMIN_SECTION = re.compile(r"^(Listening scripts|Language-use and reading rationales)$")

#: Lines that can only begin a paragraph in the Administrator Pack.
_ADMIN_OPENERS = (
    re.compile(r"^Q\d{1,2}\s*·"),
    re.compile(r"^(Question|Key|Target):"),
    ADMIN_FORM,
    _ADMIN_SECTION,
    SPEAKER_TURN,
)

#: Administrator Pack furniture.
_ADMIN_FURNITURE = (
    re.compile(r"^Meli\s*·\s*CLE"),
    re.compile(r"^Internal use\s*·"),
    re.compile(r"^Do not distribute this section"),
    re.compile(r"^Read/play each script twice"),
)


def read_admin_pack(
    path: Path,
) -> tuple[dict[tuple[str, int], dict[str, Any]], dict[tuple[str, int], dict[str, str]]]:
    """Read transcripts, answer texts, rationales and the printed key table."""
    lines = read_lines(path)
    margin = right_margin(lines)
    body = [line for line in lines if not is_furniture(line.text.strip(), _ADMIN_FURNITURE)]
    # Scripts and rationales are free prose and could plausibly run over a page,
    # and paragraph grouping never spans pages. Applied here for the same reason
    # it is applied to the booklet: a transcript silently gaining a line break
    # mid-sentence is what a proctor would then read aloud.
    assert_no_severed_page_break(path.name, body, margin, _ADMIN_OPENERS)
    paragraphs = group_paragraphs(body, margin=margin, openers=_ADMIN_OPENERS)

    entries: dict[tuple[str, int], dict[str, Any]] = {}
    form_code: str | None = None
    current: tuple[str, int] | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        if current is not None:
            _absorb(entries[current], buffer)
        buffer = []

    for paragraph in paragraphs:
        text = paragraph.text

        form_match = ADMIN_FORM.match(text)
        if form_match:
            flush()
            current = None
            form_code = form_match.group(1) or form_match.group(2)
            continue

        heading = ADMIN_HEADING.match(text) if form_code else None
        if heading:
            flush()
            number = int(heading.group(1))
            current = (form_code, number)
            if current in entries:
                raise ExtractError(f"Administrator Pack repeats Form {form_code} Q{number}")
            entries[current] = {
                "item_id": heading.group(2),
                "legacy_band": int(heading.group(3)),
            }
            continue

        if _ADMIN_SECTION.match(text):
            # A section heading ends the previous item but opens nothing.
            flush()
            current = None
            continue

        if current is not None:
            buffer.append(text)

    flush()
    return entries, _read_admin_key_tables(lines)


def _absorb(entry: dict[str, Any], buffer: Sequence[str]) -> None:
    """Split one item's paragraphs into script, answer text and rationale.

    Position relative to the "Key:" line is what distinguishes a listening
    script from a rationale: both are free prose. Before the key it is the
    script the proctor reads; after it, the defence of the key. Matching on a
    prefix instead would silently drop every rationale that opens with "The
    decisive evidence is…" rather than "Option D…".
    """
    transcript: list[str] = []
    rationale: list[str] = []
    seen_key = False
    for line in buffer:
        if line.startswith("Key:"):
            seen_key = True
            match = ADMIN_KEY.match(line)
            if match:
                entry["correct_answer"] = match.group(1)
                entry["answer_text"] = clean(match.group(2))
                if match.group(3):
                    rationale.append(clean(match.group(3)))
        elif line.startswith("Question:"):
            entry["admin_question"] = clean(line[len("Question:") :])
        elif line.startswith("Target:"):
            entry["admin_target"] = clean(line[len("Target:") :])
        elif seen_key:
            rationale.append(line)
        else:
            transcript.append(line)
    if transcript:
        entry["transcript"] = "\n".join(transcript)
    if rationale:
        entry["rationale"] = " ".join(rationale)


def _read_admin_key_tables(
    lines: Sequence[Line],
) -> dict[tuple[str, int], dict[str, str]]:
    """Parse the printed "No. / Key / Band / Skill / Item ID" tables.

    This is the artefact a proctor actually marks against, so it is a third
    independent statement of the key. Rows are recovered by grouping cells that
    share a baseline and reading them left to right.
    """
    rows: dict[tuple[str, int, float], list[Line]] = {}
    form_code: str | None = None
    collecting = False

    for line in lines:
        text = line.text.strip()
        match = ADMIN_FORM.match(text)
        if match:
            form_code = match.group(1) or match.group(2)
            collecting = True
            continue
        if _ADMIN_SECTION.match(text):
            collecting = False
            continue
        if not (collecting and form_code) or is_furniture(text, _ADMIN_FURNITURE):
            continue
        rows.setdefault((form_code, line.page, round(line.y0, 1)), []).append(line)

    out: dict[tuple[str, int], dict[str, str]] = {}
    for (code, _page, _y0), cells in rows.items():
        ordered = sorted(cells, key=lambda cell: cell.x0)
        if len(ordered) != 5:
            continue
        values = [cell.text.strip() for cell in ordered]
        if not values[0].isdigit():
            continue
        number = int(values[0])
        if not 1 <= number <= ITEMS_PER_FORM:
            continue
        if (code, number) in out:
            raise ExtractError(f"Administrator Pack key table repeats {code} Q{number}")
        out[(code, number)] = {
            "correct_answer": values[1],
            "band_label": values[2],
            "skill": values[3],
            "item_id": values[4],
        }
    return out
