"""Blueprint constants and the reader for the student booklet.

A placement source package is three artefacts, and the split between the
readers is the security story of this test:

* :func:`read_student_form`, here, reads the **student-safe** surface (passage,
  stem, options) out of the booklet a learner is handed, so nothing restricted
  can leak into the delivery payload by construction;
* ``placement_workbook`` and ``placement_admin_pack`` read the **restricted**
  surface (key, answer text, rationale, listening script, reference band) out
  of the two controlled artefacts.

Assembly, cross-checking and validation live in ``extract_placement_bank``;
these modules only turn files into dictionaries. Blueprint facts shared by all
three live here, since the booklet is the artefact they describe.

v1.3 ships PDFs where v1.2 shipped DOCX, so paragraphs are reconstructed from
page geometry -- see ``pdf_layout`` for how and why.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Sequence

from scripts.pdf_layout import (
    WRAP_TOLERANCE,
    X_TOLERANCE,
    Line,
    Paragraph,
    collapse,
    group_paragraphs,
    read_lines,
    right_margin,
    text_signature,
)

PACKAGE_VERSION = "v1.3"
FORMS = ("A", "B", "C", "D", "E")
ITEMS_PER_FORM = 30
BANDS = (1, 2, 3, 4, 5, 6)

#: Section boundaries are fixed by the published blueprint (12 / 6 / 12) and are
#: asserted rather than inferred, so a re-ordered source fails loudly.
SECTION_BY_QUESTION = {
    **{q: "listening" for q in range(1, 13)},
    **{q: "language_use" for q in range(13, 19)},
    **{q: "reading" for q in range(19, 31)},
}

#: Workbook ``Skill`` -> our section key. The workbook says "Vocabulary" for the
#: middle block while every learner-facing artefact says "Language Use"; the
#: booklet heading and the Summary sheet both use "Language Use", so that wins.
SKILL_TO_SECTION = {
    "Listening": "listening",
    "Vocabulary": "language_use",
    "Language Use": "language_use",
    "Reading": "reading",
}

#: A line like "A. 老师     B. 医生" -- the booklet lays options two per line,
#: separated only by a run of spaces.
_OPTION_PAIR = re.compile(r"([A-F])\.\s*(.*?)(?=\s{2,}[A-F]\.|$)", re.DOTALL)
_QUESTION_START = re.compile(r"^(\d{1,2})\.\s*(.*)$", re.DOTALL)
_OPTION_START = re.compile(r"^[A-F]\.\s")
CLOZE_PROMPT = re.compile(r"^请选择最合适的一项填入第（(\d{1,2})）空。$")
CLOZE_BLANK = re.compile(r"（(\d{1,2})）\s*_")
_ORDER_LINE = "Order / 顺序"
#: A speaker turn: up to five Han characters then a full-width colon. Used as a
#: paragraph opener so two turns of one dialogue never fuse into one line.
#: Shared with the Administrator Pack reader, whose interview scripts have the
#: same shape.
SPEAKER_TURN = re.compile(r"^[一-鿿]{1,5}：")
_PURPOSE = re.compile(r"^Purpose:\s*(.+)$")
_PRIVACY = re.compile(r"^Privacy:\s*(.+)$")

#: Punctuation that closes a sentence, full-width and ASCII. A line ending in
#: one of these is finished, whatever it does to the right margin.
_SENTENCE_ENDINGS = ("。", "！", "？", "；", ".", "!", "?")

#: Booklet furniture that sits between questions and must never be mistaken for
#: item text. Without this, a section heading and its "Questions 19-30 · about
#: 13 minutes" descriptor get absorbed as the stem of the *preceding* item, and
#: the running page header would land in the middle of a passage.
_FURNITURE = (
    re.compile(r"^(Listening|Language Use|Reading|Instructions|Answer Sheet)\s*/"),
    re.compile(r"^Questions \d{1,2}-\d{1,2}\s*·"),
    re.compile(r"^Internal use\s*·"),
    re.compile(r"^MELI\s*·"),
    re.compile(r"^Meli\s*·\s*CLE"),
    re.compile(r"^Form [A-E]\s*·"),
    re.compile(r"^30-minute internal diagnostic"),
    re.compile(r"^Do not open the next page"),
)

#: Lines that can only begin a paragraph in a student booklet.
_BOOKLET_OPENERS = (
    re.compile(r"^\d{1,2}\.\s"),
    _OPTION_START,
    re.compile(r"^Order / 顺序"),
    SPEAKER_TURN,
    CLOZE_PROMPT,
)


class ExtractError(RuntimeError):
    """Raised when the source package does not match the published blueprint."""


@dataclass
class RawItem:
    """One question as read from the student booklet (safe fields only)."""

    question_number: int
    section: str
    passage: str | None = None
    stem: str = ""
    prompt: str | None = None
    options: list[dict[str, str]] = field(default_factory=list)
    is_sequence: bool = False
    #: The "Order / 顺序: ___ - ___ - ___" line as printed, kept only so the
    #: losslessness check can account for it. Never delivered.
    order_line: str | None = None


def clean(text: str) -> str:
    """Normalise whitespace without touching CJK content.

    NFC only. The booklets mix ideographic space (U+3000) inside cloze brackets
    with ASCII spaces around option letters; collapsing the former would corrupt
    the rendered blank, so only ASCII runs are collapsed.
    """
    return collapse(unicodedata.normalize("NFC", text).replace(" ", " "))


def is_furniture(line: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.match(line) for pattern in patterns)


def _parse_options(raw_line: str) -> list[tuple[str, str]]:
    """Pull ``(letter, text)`` pairs out of one booklet option line.

    Takes the *raw* paragraph text: the option boundary is a run of two or more
    spaces, so this must run before ASCII whitespace is collapsed.
    """
    found = [(m.group(1), clean(m.group(2))) for m in _OPTION_PAIR.finditer(raw_line)]
    return [(letter, text) for letter, text in found if text]


# --------------------------------------------------------------------------
# Student booklet: the safe surface
# --------------------------------------------------------------------------


def _booklet_body(path: Path) -> list[Line]:
    """The printed paper, minus furniture and minus the answer sheet.

    The answer sheet is cut *before* anything else. Its grid of bare row numbers
    is not furniture by any pattern -- "16" is just a number -- so left in place
    it is absorbed as body text by the last question on the paper. Cutting here
    also keeps the answer-sheet columns out of the right-margin measurement.

    Furniture goes next, so the running header and footer cannot land in the
    middle of an item.
    """
    lines = read_lines(path)
    end = next(
        (i for i, line in enumerate(lines) if line.text.strip().startswith("Answer Sheet")),
        len(lines),
    )
    if end == len(lines):
        raise ExtractError(f"{path.name}: no answer sheet found; booklet may be truncated")
    return [line for line in lines[:end] if not is_furniture(line.text.strip(), _FURNITURE)]


def assert_no_severed_page_break(
    where: str,
    lines: Sequence[Line],
    margin: float,
    openers: Sequence[re.Pattern[str]],
) -> None:
    """Refuse a document whose text runs across a page boundary.

    :func:`pdf_layout.group_paragraphs` never joins across pages, deliberately:
    a paragraph that happens to end flush with the margin at the foot of a page
    would otherwise fuse with whatever starts the next one, and that guess is
    unrecoverable. Every v1.3 artefact begins a new block on each page, so the
    rule costs nothing today.

    It would cost a lot silently, though. Text split at a page break still
    contains every character in the right order, so the losslessness check
    passes while the split lands in the wrong field -- half a cloze in ``stem``
    instead of ``passage``, or a stray line break dropped into the middle of a
    sentence a proctor then reads aloud. Detecting the layout that would cause
    it, and stopping, is the difference between a loud failure and a wrong item.

    A line that ends a sentence is not a candidate. Reaching the margin is not
    the same as being cut off, and the Administrator Pack routinely ends a
    complete "Key: …。" line flush at the foot of a page with a new paragraph
    overleaf. Without this the guard cries wolf on correct layout, which is the
    fastest way to have it disabled.
    """
    for previous, current in pairwise(lines):
        if current.page == previous.page:
            continue
        if abs(current.x0 - previous.x0) > X_TOLERANCE:
            continue
        if previous.x1 < margin - WRAP_TOLERANCE:
            continue
        if previous.text.rstrip().endswith(_SENTENCE_ENDINGS):
            continue
        if any(pattern.match(current.text.strip()) for pattern in openers):
            continue
        raise ExtractError(
            f"{where}: text appears to continue from page "
            f"{previous.page} to {current.page} ({previous.text.strip()[-20:]!r} -> "
            f"{current.text.strip()[:20]!r}). Paragraph grouping cannot span "
            f"pages, so this layout needs handling before the bank is trusted."
        )


def _read_claim_boundary(lines: Sequence[Line]) -> dict[str, str]:
    """Read the Purpose and Privacy statements off the cover page.

    These sit in callout boxes that wrap at their own, narrower, margin, so the
    body-column wrap rule does not see their continuation lines.

    Consumption therefore runs to the *end of the block* -- the next label, a
    change of indent, or a page break -- and only then requires the result to be
    a complete sentence. Stopping at the first full stop instead would look
    simpler and would silently truncate at an internal abbreviation, producing a
    fragment that still ends in "." and so passes the completeness check. A
    quietly shortened purpose statement is a claim-boundary defect, not a
    cosmetic one, so the check has to be one the failure cannot satisfy.
    """
    out: dict[str, str] = {}
    for index, line in enumerate(lines):
        # Matched against the *raw* text: an English line wraps with its
        # trailing space intact, and that space is the only thing separating
        # "…examination or" from "score report.".
        for name, pattern in (("purpose", _PURPOSE), ("privacy", _PRIVACY)):
            match = pattern.match(line.text.lstrip())
            if match:
                break
        else:
            continue
        if name in out:
            continue
        parts = [match.group(1)]
        for following in lines[index + 1 :]:
            text = following.text.lstrip()
            if following.page != line.page:
                break
            if abs(following.x0 - line.x0) > X_TOLERANCE:
                break
            if _PURPOSE.match(text) or _PRIVACY.match(text):
                break
            parts.append(following.text)
        statement = clean("".join(parts))
        if not statement.endswith("."):
            raise ExtractError(
                f"{name} statement is not a complete sentence: {statement!r}"
            )
        out[name] = statement
    return out


def read_student_form(path: Path, form_code: str) -> tuple[list[RawItem], dict[str, str]]:
    """Read the 30 safe question surfaces and the claim boundary from a booklet."""
    lines = _booklet_body(path)
    margin = right_margin(lines)
    assert_no_severed_page_break(
        f"Form {form_code}", lines, margin, _BOOKLET_OPENERS
    )
    boundary = _read_claim_boundary(lines)
    paragraphs = group_paragraphs(lines, margin=margin, openers=_BOOKLET_OPENERS)

    items: list[RawItem] = []
    current: RawItem | None = None
    # Text paragraphs accumulated since the question opened but before its
    # options, each with the left edge it was printed at. The indent is what
    # separates the stimulus from the question asked about it.
    body: list[tuple[float, str]] = []

    def close() -> None:
        nonlocal current, body
        if current is None:
            return
        _finalise(current, body)
        items.append(current)
        current = None
        body = []

    for paragraph in paragraphs:
        opening = _opens_question(paragraph.text, current)
        if opening is not None:
            close()
            current = RawItem(
                question_number=opening, section=SECTION_BY_QUESTION[opening]
            )
            first = clean(_QUESTION_START.match(paragraph.text).group(2))
            body = [(paragraph.x0, first)] if first else []
            continue
        if current is not None:
            _absorb_paragraph(current, paragraph, body)

    close()

    if len(items) != ITEMS_PER_FORM:
        raise ExtractError(
            f"Form {form_code}: expected {ITEMS_PER_FORM} questions, parsed {len(items)}"
        )
    _assert_lossless(form_code, items, lines)
    for name in ("purpose", "privacy"):
        if not boundary.get(name):
            raise ExtractError(f"Form {form_code}: booklet has no {name} statement")
    return items, boundary


def _opens_question(line: str, current: RawItem | None) -> int | None:
    """The question number this paragraph opens, or ``None``.

    A numbered paragraph only opens a question when the number is exactly the
    next one expected. Passages legitimately contain "…3.5倍" style text, and
    option lines start with a letter, so both are rejected here.
    """
    match = _QUESTION_START.match(line)
    if not match or _OPTION_START.match(line):
        return None
    expected = (current.question_number + 1) if current else 1
    if expected > ITEMS_PER_FORM or int(match.group(1)) != expected:
        return None
    return expected


def _absorb_paragraph(
    item: RawItem, paragraph: Paragraph, body: list[tuple[float, str]]
) -> None:
    """File one paragraph of an open question under what it actually is."""
    line = paragraph.text
    if line.startswith(_ORDER_LINE):
        item.is_sequence = True
        item.order_line = line
    elif _OPTION_START.match(line):
        # From the *raw* text: the option boundary is a run of spaces, which
        # the cleaned text has already collapsed to one.
        for letter, text in _parse_options(paragraph.raw):
            item.options.append({"letter": letter, "text": text})
    elif CLOZE_PROMPT.match(line):
        item.prompt = line
    else:
        body.append((paragraph.x0, line))


def _assert_lossless(form_code: str, items: Sequence[RawItem], lines: Sequence[Line]) -> None:
    """Reconstruct the question region and require it to equal the source, exactly.

    Paragraph grouping decides *where* line breaks fall, never *which*
    characters exist. So if the 30 items are re-rendered in printed order --
    number, stimulus, question, cloze instruction, options, ordering slots --
    and every space is dropped from both sides, the result must be
    character-for-character the text the booklet prints from question 1 onward.

    Equality, not containment, is the point. A substring check passes on a field
    that silently lost its last line and on one that swallowed its neighbour;
    only equality proves nothing was dropped, duplicated, reordered or invented
    between the controlled artefact and what a learner will be shown.
    """
    start = next(
        (i for i, line in enumerate(lines) if _QUESTION_START.match(line.text.strip())),
        None,
    )
    if start is None:
        raise ExtractError(f"Form {form_code}: no numbered question found")
    printed = text_signature(lines[start:])

    rebuilt: list[str] = []
    for item in items:
        rebuilt.append(f"{item.question_number}.")
        rebuilt.append(item.passage or "")
        rebuilt.append(item.stem)
        rebuilt.append(item.prompt or "")
        rebuilt.extend(f"{o['letter']}.{o['text']}" for o in item.options)
        rebuilt.append(item.order_line or "")
    rebuilt_signature = re.sub(r"\s+", "", "".join(rebuilt))

    if rebuilt_signature != printed:
        raise ExtractError(
            f"Form {form_code}: reconstruction does not match the printed paper "
            f"({_first_divergence(rebuilt_signature, printed)})"
        )


def _first_divergence(rebuilt: str, printed: str) -> str:
    """Where the two strings part company, so a failure is actionable."""
    limit = min(len(rebuilt), len(printed))
    index = next((i for i in range(limit) if rebuilt[i] != printed[i]), limit)
    return (
        f"diverges at character {index}: "
        f"rebuilt {rebuilt[index:index + 40]!r} vs printed {printed[index:index + 40]!r}"
    )


def _finalise(item: RawItem, body: list[tuple[float, str]]) -> None:
    """Split the accumulated text into passage vs stem, using the indentation.

    The booklet prints the stimulus at the body's left edge and indents the
    question asked about it. Reading the split off that geometry rather than
    off position ("the last paragraph is the stem") matters because the two
    disagree exactly when something has gone wrong: if two paragraphs were
    wrongly fused or wrongly separated, a positional rule still produces a
    confident, plausible, wrong answer, and the losslessness check cannot see
    it because no character moved. The indent is independent evidence.

    An item with no indented paragraph is a single-paragraph item (a bare
    question, or a cloze whose text is the item) and needs no split.
    """
    paragraphs = [(x0, text) for x0, text in body if text]
    if paragraphs:
        left = min(x0 for x0, _ in paragraphs)
        indented = [i for i, (x0, _) in enumerate(paragraphs) if x0 - left > X_TOLERANCE]

        if not indented:
            if len(paragraphs) > 1:
                raise ExtractError(
                    f"Q{item.question_number}: {len(paragraphs)} paragraphs at one "
                    f"indent, so the stimulus and the question cannot be told apart"
                )
            item.stem = paragraphs[0][1]
        elif len(indented) > 1 or indented[-1] != len(paragraphs) - 1:
            raise ExtractError(
                f"Q{item.question_number}: expected one indented question after the "
                f"stimulus, found {len(indented)} at positions {indented}"
            )
        else:
            item.passage = "\n".join(text for _, text in paragraphs[:-1])
            item.stem = paragraphs[-1][1]

    # Cloze items carry their instruction in `prompt`; the passage IS the item,
    # so a cloze whose text landed in `stem` should present as a passage.
    if item.prompt and item.passage is None and item.stem:
        item.passage = item.stem
        item.stem = ""
