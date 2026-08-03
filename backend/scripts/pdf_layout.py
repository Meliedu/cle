"""Reconstruct logical paragraphs from a PDF's visual lines.

Why this exists
---------------
The v1.2 placement package shipped DOCX, where one paragraph is one paragraph.
The v1.3 package ships **PDF only**, and a PDF has no paragraphs: it has glyphs
at coordinates. The renderer hard-wraps a passage at the column edge, so

    28. 有人把"练习"理解为把同一件事重复很多遍。重复当然有价值，但如果每次都按照原来的方法进行，错误
    也可能被一起固定下来。更有效的练习往往包含三个步骤：...

arrives as two lines that are one sentence, while

    女：你妈妈在哪儿工作？
    男：她在饭店工作。

arrives as two lines that are genuinely two. Getting that wrong corrupts the
item: the first case would render a stray line break mid-sentence to a learner,
and the second would glue two speakers into one turn.

Chinese text gives no whitespace cue at a wrap, so the distinction is recovered
from geometry plus a small set of structural openers:

* **Indentation.** The booklets use three left edges -- stimulus, stem, options
  -- so a change of ``x0`` is always a new paragraph.
* **Right margin.** A wrapped line is one the renderer could not fit another
  glyph onto, so the line *before* a continuation always reaches the margin. A
  line whose predecessor stopped short of the margin therefore starts a new
  paragraph. This is the load-bearing rule.
* **Openers.** Same indent *and* a full-width predecessor still happens between
  two speaker turns or two option pairs, so the caller supplies patterns that
  can only start a paragraph.

Joining is plain concatenation. That is deliberate and it is why English and
Chinese both work: the extractor keeps each line's trailing space, and a CJK
wrap has none while an English wrap does, so the source's own spacing decides.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import fitz  # PyMuPDF

#: Two lines are at the same indent if their left edges are within this many
#: points. Real indent steps in these documents are >= 7pt; sub-pixel jitter
#: from the renderer is < 1pt.
X_TOLERANCE = 3.0

#: How close to the right margin a line must end to be "full width". One CJK
#: glyph at the booklets' body size is ~10.8pt, so a wrapped line always ends
#: within one glyph of the margin; 12pt keeps a small safety margin without
#: swallowing a paragraph's genuinely short final line.
WRAP_TOLERANCE = 12.0


@dataclass(frozen=True)
class Line:
    """One rendered line of text with the geometry needed to group it."""

    page: int
    x0: float
    y0: float
    x1: float
    text: str


@dataclass(frozen=True)
class Paragraph:
    """One logical paragraph: the unit a DOCX would have given us directly.

    ``raw`` keeps the join exactly as the source spaced it; ``text`` collapses
    ASCII runs for matching. Both are needed because the booklets separate the
    two options on a line with a *run* of spaces ("A. 老师     B. 医生"), so
    collapsing first would destroy the only separator there is.
    """

    page: int
    x0: float
    y0: float
    text: str
    raw: str


def _normalise(text: str) -> str:
    """NFC, and fold NBSP to a plain space.

    U+3000 (ideographic space) is deliberately preserved: in these booklets it
    is the rendered blank inside a cloze bracket "（ ）", so folding it would
    change what the learner is asked to fill in.
    """
    return unicodedata.normalize("NFC", text).replace(" ", " ")


def read_lines(path: Path) -> list[Line]:
    """Every non-empty text line in the document, in reading order.

    PyMuPDF emits blocks in generation order, which puts the page header and
    footer first, so the result is re-sorted by position. ``y0`` is rounded
    before sorting so that the cells of one table row -- which share a baseline
    but differ by a hair -- stay in left-to-right order rather than shuffling.
    """
    lines: list[Line] = []
    with fitz.open(str(path)) as document:
        for number, page in enumerate(document, start=1):
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:  # 0 == text; images carry no lines
                    continue
                for line in block["lines"]:
                    text = _normalise("".join(span["text"] for span in line["spans"]))
                    if not text.strip():
                        continue
                    x0, y0, x1, _ = line["bbox"]
                    lines.append(Line(number, round(x0, 2), round(y0, 2), round(x1, 2), text))
    lines.sort(key=lambda line: (line.page, round(line.y0, 1), line.x0))
    return lines


def right_margin(lines: Sequence[Line], *, body_x0: float | None = None) -> float:
    """The x-coordinate the renderer wraps at.

    Measured from the body column only. Page furniture (a right-aligned footer)
    and table cells sit outside that column and would otherwise pull the margin
    past where body text can actually reach, which would make every wrapped line
    look like it stopped short and defeat the wrap rule entirely.
    """
    if body_x0 is None:
        body_x0 = body_indent(lines)
    candidates = [
        line.x1 for line in lines if abs(line.x0 - body_x0) <= X_TOLERANCE
    ]
    if not candidates:
        raise ValueError("no lines at the body indent; cannot locate the right margin")
    return max(candidates)


def body_indent(lines: Sequence[Line]) -> float:
    """The left edge of the main text column: the most common ``x0``."""
    counts: dict[float, int] = {}
    for line in lines:
        # Bucket to the tolerance so jitter does not split one indent in two.
        bucket = round(line.x0 / X_TOLERANCE) * X_TOLERANCE
        counts[bucket] = counts.get(bucket, 0) + 1
    bucket = max(counts, key=lambda key: counts[key])
    at_bucket = [
        line.x0 for line in lines if abs(line.x0 - bucket) <= X_TOLERANCE
    ]
    return min(at_bucket)


def group_paragraphs(
    lines: Iterable[Line],
    *,
    margin: float,
    openers: Sequence[re.Pattern[str]] = (),
    wrap_tolerance: float = WRAP_TOLERANCE,
) -> list[Paragraph]:
    """Fold rendered lines back into logical paragraphs.

    A line continues the current paragraph only when all three hold: it sits at
    the same indent, the previous line reached the right margin, and it does not
    match a structural opener. Any one of those failing starts a new paragraph.
    """
    paragraphs: list[Paragraph] = []
    buffer: list[str] = []
    start: Line | None = None
    previous: Line | None = None

    def flush() -> None:
        nonlocal buffer, start
        if start is not None and buffer:
            raw = "".join(buffer)
            text = collapse(raw)
            if text:
                paragraphs.append(
                    Paragraph(start.page, start.x0, start.y0, text, raw.strip())
                )
        buffer = []
        start = None

    for line in lines:
        continues = (
            start is not None
            and previous is not None
            and line.page == previous.page
            and abs(line.x0 - start.x0) <= X_TOLERANCE
            and previous.x1 >= margin - wrap_tolerance
            and not any(pattern.match(line.text.strip()) for pattern in openers)
        )
        if not continues:
            flush()
            start = line
        buffer.append(line.text)
        previous = line

    flush()
    return paragraphs


def collapse(text: str) -> str:
    """Collapse ASCII whitespace runs, leaving CJK spacing untouched."""
    return re.sub(r"[ \t]+", " ", text).strip()


def text_signature(lines: Iterable[Line]) -> str:
    """All characters of a line sequence with whitespace removed.

    Used as a round-trip invariant: paragraph grouping decides *where* breaks
    fall, never *which* characters exist, so the signature of the regrouped text
    must equal the signature of the lines it came from. That catches a dropped
    or duplicated line, which is the failure mode a spot-check would miss.
    """
    return re.sub(r"\s+", "", "".join(line.text for line in lines))
