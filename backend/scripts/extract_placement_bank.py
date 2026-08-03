"""Extract the Meli placement item bank from the v1.3 teacher re-review package.

Why this exists
---------------
v1.1 shipped ``data/selected_items_v1.1.json``. **Neither v1.2 nor v1.3 ships a
machine-readable item file** -- v1.2 was DOCX + one XLSX, v1.3 is PDF + one
XLSX. So the bank has to be reconstructed, and the reconstruction has to be
reproducible and checkable rather than a one-off paste.

The safe/restricted split, and why the safe half is read from the student
booklet rather than the Administrator Pack, is documented in
``placement_sources``. This module assembles what those readers return,
cross-checks it, and validates the result against the published blueprint.

What changed for v1.3
---------------------
* The package is **PDF**, so paragraphs are reconstructed from page geometry
  (see ``pdf_layout``) instead of read off DOCX paragraph objects.
* The key is cross-checked **three ways** -- workbook ``Item Metadata``,
  workbook ``Key Matrix``, and the Administrator Pack's printed answer table --
  and any disagreement is fatal. v1.2 trusted a single source.
* The claim boundary is read out of the booklets instead of being restated in
  code, so the text shown in the app is the text printed on the learner's paper.
* The workbook gained an ``Item Review`` sheet (the teacher re-review ledger).
  It is carried through to ``restricted.teacher_review`` so CLE's review screen
  can show priority and rubric scores instead of a bare item id.
* The three v1.2 items whose key the teacher disputed were revised, so the
  hardcoded dispute list is gone. Nothing is hardcoded in its place: flags are
  derived from the sources or from mechanical checks.

Usage::

    python scripts/extract_placement_bank.py --package <dir> [--out <file>]
                                             [--previous <old bank.json>]

Output is a single versioned JSON consumed by
``app/services/placement_bank.py``. Nothing here runs at request time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

# Run as a script, so ``backend/`` is not on the path yet. Everything below is
# imported package-qualified: ``scripts`` is a real package precisely so there
# is only ever one copy of these modules. See ``scripts/__init__.py``.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Two facts this script must not restate: which flag codes stop a publication,
# and the section blueprint. Both are re-checked by the API at import and
# publish time, so a second copy here would be free to drift, and the drift
# would surface only as a summary line disagreeing with the gate. The contract
# module is dependency-free on purpose, so this stays an offline script.
from app.services.placement_contract import (  # noqa: E402
    BLOCKING_FLAG_CODES,
    EXPECTED_SECTIONS,
)
from scripts.placement_admin_pack import read_admin_pack  # noqa: E402
from scripts.placement_sources import (  # noqa: E402
    BANDS,
    CLOZE_BLANK,
    CLOZE_PROMPT,
    FORMS,
    ITEMS_PER_FORM,
    PACKAGE_VERSION,
    SKILL_TO_SECTION,
    ExtractError,
    RawItem,
    read_student_form,
)
from scripts.placement_workbook import read_workbook  # noqa: E402

VERSION_CODE = f"meli-placement-{PACKAGE_VERSION}-candidate-2026-08-03"
SOURCE_PACKAGE = f"Meli_Placement_Test_{PACKAGE_VERSION}_Teacher_Rereview_2026-08-03"
EXPECTED_SECONDS_PER_FORM = 1401
#: A multiple-choice item offers four options; an ordering item offers three
#: parts to arrange. Both are blueprint facts, not incidental.
CHOICE_OPTIONS = 4
SEQUENCE_PARTS = 3

_WORKBOOK_NAME = f"Meli_Placement_Test_{PACKAGE_VERSION}_Scoring_and_Calibration.xlsx"
_ADMIN_PACK_NAME = f"Meli_Placement_Test_{PACKAGE_VERSION}_Administrator_Pack.pdf"

#: A bare question number followed by a space, not preceded by a digit or dot.
#: Finding one inside an assembled stem means the paragraph grouper fused two
#: items, which no other check would notice.
_STRAY_QUESTION_NUMBER = re.compile(r"(?<![\d.])\d{1,2}\.\s")


def build_bank(package: Path, *, previous: dict | None = None) -> dict[str, Any]:
    """Assemble and validate the full versioned bank."""
    root = _resolve_root(package)
    workbook_path = root / _WORKBOOK_NAME
    admin_pack_path = root / _ADMIN_PACK_NAME
    for path in (workbook_path, admin_pack_path):
        if not path.exists():
            raise ExtractError(f"missing source file: {path}")

    sheets = read_workbook(workbook_path)
    metadata = sheets["metadata"]
    key_matrix = sheets["key_matrix"]
    review_ledger = sheets["review"]
    admin_entries, admin_keys = read_admin_pack(admin_pack_path)

    forms: list[dict[str, Any]] = []
    checksums = {
        workbook_path.name: _sha256(workbook_path),
        admin_pack_path.name: _sha256(admin_pack_path),
    }
    claim_boundary: dict[str, str] = {}

    for form_code in FORMS:
        booklet = root / f"Meli_Placement_Test_{PACKAGE_VERSION}_Form_{form_code}.pdf"
        if not booklet.exists():
            raise ExtractError(f"missing student booklet: {booklet}")
        checksums[booklet.name] = _sha256(booklet)

        raw_items, boundary = read_student_form(booklet, form_code)
        # Every booklet prints the same claim boundary. If one disagrees, the
        # package is internally inconsistent about what it promises a learner.
        if claim_boundary and boundary != claim_boundary:
            raise ExtractError(
                f"Form {form_code}: claim boundary differs from the earlier booklets"
            )
        claim_boundary = boundary

        items = [
            _build_item(form_code, raw, metadata, key_matrix, admin_entries, admin_keys, review_ledger)
            for raw in raw_items
        ]
        _validate_form(form_code, items)
        forms.append({"form_code": form_code, "items": items})

    _assert_item_ids_unique(forms)

    bank: dict[str, Any] = {
        "version_code": VERSION_CODE,
        "source_package": SOURCE_PACKAGE,
        "source_checksums": checksums,
        "blueprint": {
            "items_per_form": ITEMS_PER_FORM,
            "sections": dict(EXPECTED_SECTIONS),
            "items_per_band": 5,
            "bands": list(BANDS),
            "expected_seconds_per_form": EXPECTED_SECONDS_PER_FORM,
            "duration_minutes": 30,
        },
        # Read from the booklets rather than restated here, so the text a
        # learner is shown in the app is the text printed on their paper.
        "claim_boundary": {**claim_boundary, "version": PACKAGE_VERSION},
        # The workbook's own thresholds and course map, carried so the policy
        # stored against an imported version can be proved equal to them.
        "scoring_rules": sheets["rules"],
        "forms": forms,
    }
    if previous is not None:
        bank["changes_from"] = _diff_against(previous, forms)
    return bank


def _build_item(
    form_code: str,
    raw: RawItem,
    metadata: dict[tuple[str, int], dict[str, Any]],
    key_matrix: dict[tuple[str, int], dict[str, Any]],
    admin_entries: dict[tuple[str, int], dict[str, Any]],
    admin_keys: dict[tuple[str, int], dict[str, str]],
    review_ledger: dict[tuple[str, int], dict[str, Any]],
) -> dict[str, Any]:
    """Join one booklet question to its restricted metadata, checking as it goes."""
    slot = (form_code, raw.question_number)
    location = f"Form {form_code} Q{raw.question_number}"

    meta = metadata.get(slot)
    if meta is None:
        raise ExtractError(f"{location}: no workbook metadata")

    _assert_sources_agree(
        location, meta, key_matrix.get(slot), admin_keys.get(slot), admin_entries.get(slot)
    )

    # The workbook's skill and the blueprint's section for this question number
    # are two statements of the same fact, from different files.
    if SKILL_TO_SECTION.get(meta["skill"]) != raw.section:
        raise ExtractError(
            f"{location}: skill {meta['skill']!r} does not match "
            f"blueprint section {raw.section!r}"
        )

    return _assemble_item(raw, meta, admin_entries[slot], review_ledger.get(slot))


def _assert_sources_agree(
    location: str,
    meta: dict[str, Any],
    matrix: dict[str, Any] | None,
    printed: dict[str, str] | None,
    admin_entry: dict[str, Any] | None,
) -> None:
    """Three independent statements of the key must be identical.

    ``Item Metadata`` is what the scoring sheet looks up, ``Key Matrix`` is what
    the workbook prints, and the Administrator Pack table is what a proctor
    marks against. If they disagree, no answer is defensible and there is no
    basis for picking a winner, so extraction stops rather than guessing.
    """
    key = meta["correct_answer"]
    item_id = meta["item_id"]
    band = meta["legacy_band"]

    if matrix is None:
        raise ExtractError(f"{location}: absent from the workbook Key Matrix")
    if matrix["correct_answer"] != key:
        raise ExtractError(
            f"{location}: Key Matrix keys {matrix['correct_answer']!r}, "
            f"Item Metadata keys {key!r}"
        )
    if matrix["item_id"] != item_id:
        raise ExtractError(
            f"{location}: Key Matrix item id {matrix['item_id']!r} != {item_id!r}"
        )
    if matrix["legacy_band"] != band:
        raise ExtractError(
            f"{location}: Key Matrix band {matrix['legacy_band']} != {band}"
        )

    if printed is None:
        raise ExtractError(f"{location}: absent from the Administrator Pack key table")
    if printed["correct_answer"] != key:
        raise ExtractError(
            f"{location}: Administrator Pack table keys "
            f"{printed['correct_answer']!r}, workbook keys {key!r}"
        )
    if printed["item_id"] != item_id:
        raise ExtractError(
            f"{location}: Administrator Pack item id {printed['item_id']!r} != {item_id!r}"
        )
    if printed["band_label"] != f"HSK{band}":
        raise ExtractError(
            f"{location}: Administrator Pack band {printed['band_label']!r} != HSK{band}"
        )

    if not admin_entry:
        raise ExtractError(f"{location}: no Administrator Pack rationale or script")
    if admin_entry.get("item_id") != item_id:
        raise ExtractError(
            f"{location}: script heading item id "
            f"{admin_entry.get('item_id')!r} != {item_id!r}"
        )
    if admin_entry.get("legacy_band") != band:
        raise ExtractError(
            f"{location}: script heading band {admin_entry.get('legacy_band')} != {band}"
        )
    rationale_key = admin_entry.get("correct_answer")
    if rationale_key is None:
        raise ExtractError(f"{location}: Administrator Pack rationale states no key")
    if rationale_key != key:
        raise ExtractError(
            f"{location}: rationale keys {rationale_key!r}, workbook keys {key!r}"
        )


def _assemble_item(
    raw: RawItem,
    meta: dict[str, Any],
    admin_entry: dict[str, Any],
    review: dict[str, Any] | None,
) -> dict[str, Any]:
    key = meta["correct_answer"]
    letters = [option["letter"] for option in raw.options]
    flags: list[dict[str, str]] = []

    if raw.is_sequence:
        response_format = "sequence"
        # A permutation, not a membership test. "A-B" (short) and "A-A-B"
        # (repeated) both name only real options, but neither can be produced
        # by arranging the three parts on the page, so no legitimate answer
        # could ever match the key and the item would be quietly unscoreable.
        valid = sorted(key.split("-")) == sorted(letters)
    else:
        response_format = f"choice_{len(letters)}"
        valid = key in letters

    if not valid:
        # A key naming an option the booklet does not offer is unscoreable.
        # Recorded as a blocking flag rather than aborting: the bank must still
        # load so the review queue can show CLE exactly what is wrong.
        flags.append(
            {
                "code": "key_not_in_options",
                "detail": f"key {key!r} is not among the booklet options {letters}",
                "source": "extractor",
            }
        )

    flags.extend(_cloze_numbering_flags(raw))
    flags.extend(_provenance_flags(meta, review))

    return {
        "question_number": raw.question_number,
        "section": raw.section,
        "response_format": response_format,
        "option_letters": letters,
        "expected_seconds": meta["expected_seconds"],
        "audio_playback": meta["audio_playback"],
        # --- student-safe delivery surface (from the student booklet only) ---
        "safe": {
            "passage": raw.passage,
            "stem": raw.stem,
            "prompt": raw.prompt,
            "options": raw.options,
        },
        # --- restricted: never serialised into a student response ---
        "restricted": {
            "item_id": meta["item_id"],
            "slot": meta["slot"],
            "legacy_band": meta["legacy_band"],
            "skill": meta["skill"],
            "item_type": meta["item_type"],
            "workbook_response_format": meta["response_format"],
            "topic": meta["topic"],
            "subskill": meta["subskill"],
            "correct_answer": key,
            "answer_text": admin_entry.get("answer_text"),
            "rationale": admin_entry.get("rationale"),
            "transcript": admin_entry.get("transcript"),
            "target_vocabulary": meta["target_vocabulary"],
            "target_grammar": meta["target_grammar"],
            "copyright_status": meta["copyright_status"],
            "qa_status": meta["qa_status"],
            "teacher_review": review,
        },
        "teacher_flags": flags,
    }


def _provenance_flags(
    meta: dict[str, Any], review: dict[str, Any] | None
) -> list[dict[str, str]]:
    """Advisory flags derived from the sources, never from our own judgement.

    v1.2 carried a hand-maintained list of teacher annotations. Those three
    items were revised for v1.3, so instead of curating a replacement list this
    reads the workbook's own QA status: the items it marks as carrying
    incorporated feedback are exactly the ones CLE has to look at first.

    Advisory, so it surfaces in the review queue without blocking publication.
    The content owner asked for the change and the change was made; what remains
    is confirmation, which is a review task, not an unscoreable item.
    """
    status = meta.get("qa_status") or ""
    if "feedback incorporated" not in status.lower():
        return []
    detail = status
    if review and review.get("review_question"):
        detail = f"{status} ({review['review_question']})"
    return [
        {
            "code": "teacher_feedback_incorporated",
            "detail": detail,
            "source": f"workbook:Item Metadata:QA status:{PACKAGE_VERSION}",
        }
    ]


def _cloze_numbering_flags(raw: RawItem) -> list[dict[str, str]]:
    """Flag a cloze whose blank is numbered differently from its question.

    The booklet writes the blank as "（17）____" and instructs "填入第（17）空".
    Both numbers must equal the question number, or the learner is told to fill
    a blank that is not on the page. This is a mechanical check, and it is what
    caught Form B Q17 in v1.2 without anyone having to hardcode that item.
    """
    flags: list[dict[str, str]] = []
    expected = raw.question_number

    for source, text, pattern in (
        ("passage", raw.passage, CLOZE_BLANK),
        ("prompt", raw.prompt, CLOZE_PROMPT),
    ):
        if not text:
            continue
        for match in pattern.finditer(text):
            found = int(match.group(1))
            if found != expected:
                flags.append(
                    {
                        "code": "cloze_blank_number_mismatch",
                        "detail": (
                            f"{source} numbers the blank （{found}） but this is "
                            f"question {expected}"
                        ),
                        "source": "extractor",
                    }
                )
    return flags


def _assert_item_ids_unique(forms: list[dict[str, Any]]) -> None:
    """Item ids must be unique across the whole bank, not just within a form.

    ``_diff_against`` keys the previous bank by item id alone, so a duplicate
    would silently make it compare one form's item against another form's, and
    report the wrong answer to the question CLE most needs right: which keys
    moved between versions.
    """
    seen: dict[str, str] = {}
    for form in forms:
        for item in form["items"]:
            item_id = item["restricted"]["item_id"]
            where = f"Form {form['form_code']} Q{item['question_number']}"
            if item_id in seen:
                raise ExtractError(
                    f"{where}: item id {item_id!r} is already used by {seen[item_id]}"
                )
            seen[item_id] = where


def _validate_form(form_code: str, items: list[dict[str, Any]]) -> None:
    """Assert the published blueprint on the reconstructed form."""
    if len(items) != ITEMS_PER_FORM:
        raise ExtractError(f"Form {form_code}: {len(items)} items")

    sections: dict[str, int] = {}
    bands: dict[int, int] = {}
    item_ids: set[str] = set()
    for item in items:
        sections[item["section"]] = sections.get(item["section"], 0) + 1
        band = item["restricted"]["legacy_band"]
        bands[band] = bands.get(band, 0) + 1
        item_ids.add(item["restricted"]["item_id"])

    if sections != EXPECTED_SECTIONS:
        raise ExtractError(f"Form {form_code}: section counts {sections}")
    if any(bands.get(band) != 5 for band in BANDS):
        raise ExtractError(f"Form {form_code}: band counts {bands}")
    if len(item_ids) != ITEMS_PER_FORM:
        raise ExtractError(f"Form {form_code}: duplicate item ids")

    total = sum(item["expected_seconds"] for item in items)
    if total != EXPECTED_SECONDS_PER_FORM:
        raise ExtractError(
            f"Form {form_code}: expected {EXPECTED_SECONDS_PER_FORM} seconds, got {total}"
        )

    for item in items:
        _validate_item(form_code, item)


def _validate_item(form_code: str, item: dict[str, Any]) -> None:
    number = item["question_number"]
    where = f"Form {form_code} Q{number}"
    restricted = item["restricted"]
    options = item["safe"]["options"]
    letters = [option["letter"] for option in options]
    is_sequence = item["response_format"] == "sequence"

    expected_options = SEQUENCE_PARTS if is_sequence else CHOICE_OPTIONS
    if len(options) != expected_options:
        # The booklet separates two options on a line with a run of spaces. If
        # a line ever renders with one, the pair regex swallows the second
        # option into the first's text and the item loses an option while every
        # character stays present, so the losslessness check sees nothing wrong.
        raise ExtractError(
            f"{where}: {len(options)} options, expected {expected_options}"
        )
    _assert_option_count_matches_workbook(where, restricted, len(options))

    if letters != sorted(letters) or len(set(letters)) != len(letters):
        raise ExtractError(f"{where}: option letters {letters}")
    if is_sequence and letters != ["A", "B", "C"]:
        raise ExtractError(f"{where}: ordering item has options {letters}")
    texts = [option["text"] for option in options]
    if len(set(texts)) != len(texts):
        raise ExtractError(f"{where}: duplicate option text")
    if not item["safe"]["stem"] and not item["safe"]["passage"]:
        raise ExtractError(f"{where}: no stem or passage")
    if not is_sequence:
        _assert_answer_text_matches_key(where, restricted, options)

    # A question number bleeding into item text means the paragraph grouper
    # fused two items, which every other check here would happily accept.
    joined = (item["safe"]["passage"] or "") + item["safe"]["stem"]
    if _STRAY_QUESTION_NUMBER.search(joined):
        raise ExtractError(f"{where}: item text contains a question number")

    if item["section"] == "listening" and not restricted.get("transcript"):
        raise ExtractError(f"{where}: listening item has no script")
    if not restricted.get("answer_text"):
        raise ExtractError(f"{where}: no answer text in the Administrator Pack")


#: The workbook states the response format in prose, e.g. "4-option MC".
_WORKBOOK_OPTION_COUNT = re.compile(r"^(\d+)-option")


def _assert_option_count_matches_workbook(
    where: str, restricted: dict[str, Any], parsed: int
) -> None:
    """The workbook's stated option count must match what the booklet offered.

    Independent confirmation that option splitting worked. The workbook says
    "4-option MC" without knowing how the booklet lays the options out, so if
    the pair regex merged two options into one this disagrees, where nothing
    else would: a merged pair keeps every character and still yields a
    plausible-looking item.
    """
    stated = _WORKBOOK_OPTION_COUNT.match(restricted.get("workbook_response_format") or "")
    if stated and int(stated.group(1)) != parsed:
        raise ExtractError(
            f"{where}: workbook says {stated.group(1)} options, booklet parsed {parsed}"
        )


def _assert_answer_text_matches_key(
    where: str, restricted: dict[str, Any], options: list[dict[str, str]]
) -> None:
    """The Administrator Pack's answer text must be the keyed option's text.

    The pack states the key twice: once as a letter, once as the wording. Only
    the letter is cross-checked elsewhere, so a pack left unregenerated after an
    option was reworded keeps describing the old wording -- and a teacher
    reviewing that item is shown an answer that is not on the paper.
    """
    answer_text = restricted.get("answer_text") or ""
    keyed = next(
        (o["text"] for o in options if o["letter"] == restricted["correct_answer"]),
        None,
    )
    if keyed is None:
        # A key naming no option is already recorded as a blocking flag.
        return
    if re.sub(r"\s+", "", answer_text) != re.sub(r"\s+", "", keyed):
        raise ExtractError(
            f"{where}: Administrator Pack describes the key as {answer_text!r} "
            f"but the booklet option reads {keyed!r}"
        )


def _diff_against(previous: dict, forms: list[dict[str, Any]]) -> dict[str, Any]:
    """What moved since the previous bank, keyed by item id.

    Recorded in the bank so CLE can see the delta they are approving without
    diffing two 280 KB files by hand -- in particular which keys changed, which
    is the only kind of edit that silently re-scores a past attempt.
    """
    old = {
        item["restricted"]["item_id"]: item
        for form in previous.get("forms", [])
        for item in form["items"]
    }

    key_changes: list[dict[str, Any]] = []
    text_changed: list[str] = []
    whitespace_changed: list[str] = []
    added: list[str] = []
    for form in forms:
        for item in form["items"]:
            item_id = item["restricted"]["item_id"]
            before = old.pop(item_id, None)
            if before is None:
                added.append(item_id)
                continue
            if before["restricted"]["correct_answer"] != item["restricted"]["correct_answer"]:
                key_changes.append(
                    {
                        "item_id": item_id,
                        "from": before["restricted"]["correct_answer"],
                        "to": item["restricted"]["correct_answer"],
                    }
                )
            if _stable_hash(before["safe"]) == _stable_hash(item["safe"]):
                continue
            # Reporting "42 items changed" when 20 of them differ only in the
            # width of a blank would send CLE re-reading items nobody edited.
            # The two lists are kept apart so the number they act on is the
            # number of items whose wording actually moved.
            if _text_only(before["safe"]) == _text_only(item["safe"]):
                whitespace_changed.append(item_id)
            else:
                text_changed.append(item_id)

    return {
        "previous_version_code": previous.get("version_code"),
        "key_changes": sorted(key_changes, key=lambda change: change["item_id"]),
        "text_changed": sorted(text_changed),
        "whitespace_changed": sorted(whitespace_changed),
        "items_added": sorted(added),
        "items_removed": sorted(old),
    }


def _text_only(safe: dict[str, Any]) -> str:
    """The safe surface with every kind of space removed.

    v1.2 rendered the cloze blank as an ideographic space and v1.3's PDF text
    layer carries a plain one, so a raw comparison marks twenty untouched items
    as revised. ``\\s`` is Unicode-aware on a ``str`` pattern and so already
    covers U+3000, which leaves only what a reader would call a wording change.
    """
    joined = "".join(
        [
            safe.get("passage") or "",
            safe.get("stem") or "",
            safe.get("prompt") or "",
            *(f"{o['letter']}{o['text']}" for o in safe.get("options", [])),
        ]
    )
    return re.sub(r"\s+", "", joined)


def _resolve_root(package: Path) -> Path:
    """Find the directory that actually holds the v1.3 source files.

    The distributed archive unpacks with its own name repeated, so the path the
    user hands us may be the parent, the package dir, or the doubled dir.
    """
    candidates = [
        package,
        package / SOURCE_PACKAGE,
        package / SOURCE_PACKAGE / SOURCE_PACKAGE,
        *sorted(child for child in package.glob("*") if child.is_dir()),
    ]
    for candidate in candidates:
        if (candidate / _ADMIN_PACK_NAME).exists():
            return candidate
    raise ExtractError(
        f"no {_ADMIN_PACK_NAME} under {package} (tried: "
        + ", ".join(str(c) for c in candidates)
        + ")"
    )


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summarise(bank: dict[str, Any]) -> None:
    items = [item for form in bank["forms"] for item in form["items"]]
    flagged = [item for item in items if item["teacher_flags"]]
    blocking = [
        item
        for item in flagged
        if any(flag["code"] in BLOCKING_FLAG_CODES for flag in item["teacher_flags"])
    ]
    print(f"  {len(bank['forms'])} forms, {len(items)} items")
    print(f"  {len(flagged)} flagged, {len(blocking)} with a publication-blocking flag")

    changes = bank.get("changes_from")
    if not changes:
        return
    print(
        f"  vs {changes['previous_version_code']}: "
        f"{len(changes['key_changes'])} key change(s), "
        f"{len(changes['text_changed'])} with revised wording, "
        f"{len(changes['whitespace_changed'])} whitespace-only, "
        f"{len(changes['items_added'])} added, {len(changes['items_removed'])} removed"
    )
    for change in changes["key_changes"]:
        print(f"    key {change['item_id']}: {change['from']} -> {change['to']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "app" / "data" / "placement" / f"meli-placement-{PACKAGE_VERSION}.json",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        default=None,
        help="a prior bank JSON to record the key/text delta against",
    )
    args = parser.parse_args(argv)

    previous = None
    if args.previous is not None:
        if not args.previous.exists():
            raise ExtractError(f"previous bank not found: {args.previous}")
        previous = json.loads(args.previous.read_text(encoding="utf-8"))

    bank = build_bank(args.package, previous=previous)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(bank, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )

    print(f"wrote {args.out}")
    _summarise(bank)
    return 0


if __name__ == "__main__":
    sys.exit(main())
