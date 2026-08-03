"""Load a versioned item bank into the database, and gate its publication.

The loader is deliberately import-once-then-immutable. A published version's
items are never edited in place: a content change means a new version code, so
every scored attempt keeps pointing at the exact content it was scored against.

The preflight is the publication gate. It refuses to publish a version whose
content the people who own it have not settled -- most importantly, a version
containing an item whose key a teacher has disputed. That is not a
belt-and-braces nicety: the v1.2 package shipped two such items, and scoring
one of them would have produced a number nobody could defend. v1.3 revised
them, so the gate now passes on the real package; it stays exactly as strict,
because what changed is the content, not the standard.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.placement import (
    PlacementForm,
    PlacementItem,
    PlacementItemKey,
    PlacementTestVersion,
)

# Re-exported: these are the contract the offline extractor shares with this
# module, and callers here have always reached for them by this name.
from app.services.placement_contract import (  # noqa: F401
    BLOCKING_FLAG_CODES,
    EXPECTED_ITEMS_PER_BAND,
    EXPECTED_ITEMS_PER_FORM,
    EXPECTED_SECTIONS,
    flag_severity,
)

BANK_DIR = Path(__file__).resolve().parents[1] / "data" / "placement"


def annotate_flags(flags: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Copy stored flags with their severity resolved for display."""
    return [{**flag, "severity": flag_severity(flag.get("code"))} for flag in flags or []]


class PlacementBankError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreflightFinding:
    code: str
    severity: str  # "blocking" | "advisory"
    detail: str
    form_code: str | None = None
    question_number: int | None = None
    external_item_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "detail": self.detail,
            "form_code": self.form_code,
            "question_number": self.question_number,
            "external_item_id": self.external_item_id,
        }


@dataclass(frozen=True)
class PreflightResult:
    version_code: str
    findings: tuple[PreflightFinding, ...]

    @property
    def blocking(self) -> tuple[PreflightFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "blocking")

    @property
    def can_publish(self) -> bool:
        return not self.blocking

    def as_dict(self) -> dict[str, Any]:
        return {
            "version_code": self.version_code,
            "can_publish": self.can_publish,
            "blocking_count": len(self.blocking),
            "findings": [f.as_dict() for f in self.findings],
        }


def load_bank_file(path: Path | None = None, *, version_code: str | None = None) -> dict:
    """Read a bank JSON off disk.

    Not cached: this runs at import/publish time, never in a request path.
    """
    if path is None:
        if version_code is None:
            raise PlacementBankError("NO_BANK", "need a path or a version code")
        path = BANK_DIR / f"{version_code}.json"
    if not path.exists():
        raise PlacementBankError("NO_BANK", f"item bank not found at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def blueprint_hash(bank: Mapping[str, Any]) -> str:
    """Hash the *shape* of the bank, not its prose.

    Deliberately excludes item text: the point is to detect a structural change
    (a form losing an item, a band count shifting), which is what makes results
    incomparable. Prose changes are caught by the per-form content hash.
    """
    shape = [
        {
            "form": form["form_code"],
            "items": [
                {
                    "q": item["question_number"],
                    "section": item["section"],
                    "band": item["restricted"]["legacy_band"],
                    "format": item["response_format"],
                    "options": len(item["safe"]["options"]),
                }
                for item in sorted(form["items"], key=lambda i: i["question_number"])
            ],
        }
        for form in sorted(bank["forms"], key=lambda f: f["form_code"])
    ]
    return _stable_hash(shape)


def form_content_hash(form: Mapping[str, Any]) -> str:
    """Hash the student-visible surface of one form."""
    return _stable_hash(
        [
            {
                "q": item["question_number"],
                "passage": item["safe"]["passage"],
                "stem": item["safe"]["stem"],
                "prompt": item["safe"]["prompt"],
                "options": item["safe"]["options"],
            }
            for item in sorted(form["items"], key=lambda i: i["question_number"])
        ]
    )


def form_key_hash(form: Mapping[str, Any]) -> str:
    """Hash the keys of one form, so a key change is detectable on its own."""
    return _stable_hash(
        [
            {
                "q": item["question_number"],
                "id": item["restricted"]["item_id"],
                "key": item["restricted"]["correct_answer"],
            }
            for item in sorted(form["items"], key=lambda i: i["question_number"])
        ]
    )


def preflight_bank(bank: Mapping[str, Any]) -> PreflightResult:
    """Check a bank against the published blueprint and its own flags.

    Runs on the in-memory bank so it can gate an import as well as a publish.
    """
    findings: list[PreflightFinding] = []
    forms = bank.get("forms") or []

    if len(forms) != 5:
        findings.append(
            PreflightFinding(
                code="form_count",
                severity="blocking",
                detail=f"expected 5 forms, found {len(forms)}",
            )
        )

    for form in forms:
        code = form["form_code"]
        items = form["items"]

        if len(items) != EXPECTED_ITEMS_PER_FORM:
            findings.append(
                PreflightFinding(
                    code="item_count",
                    severity="blocking",
                    detail=f"expected {EXPECTED_ITEMS_PER_FORM} items, found {len(items)}",
                    form_code=code,
                )
            )

        sections: dict[str, int] = {}
        bands: dict[int, int] = {}
        for item in items:
            sections[item["section"]] = sections.get(item["section"], 0) + 1
            band = item["restricted"]["legacy_band"]
            bands[band] = bands.get(band, 0) + 1

        for section, expected in EXPECTED_SECTIONS.items():
            if sections.get(section, 0) != expected:
                findings.append(
                    PreflightFinding(
                        code="section_blueprint",
                        severity="blocking",
                        detail=(
                            f"section {section}: expected {expected}, "
                            f"found {sections.get(section, 0)}"
                        ),
                        form_code=code,
                    )
                )
        for band in range(1, 7):
            if bands.get(band, 0) != EXPECTED_ITEMS_PER_BAND:
                findings.append(
                    PreflightFinding(
                        code="band_blueprint",
                        severity="blocking",
                        detail=(
                            f"band {band}: expected {EXPECTED_ITEMS_PER_BAND}, "
                            f"found {bands.get(band, 0)}"
                        ),
                        form_code=code,
                    )
                )

        for item in items:
            findings.extend(_item_findings(code, item))

    if not bank.get("claim_boundary", {}).get("purpose"):
        findings.append(
            PreflightFinding(
                code="missing_claim_boundary",
                severity="blocking",
                detail=(
                    "the learner-facing purpose statement is missing; the test "
                    "cannot be delivered without its claim boundary"
                ),
            )
        )

    return PreflightResult(
        version_code=str(bank.get("version_code", "")), findings=tuple(findings)
    )


def _key_is_answerable(key: str, letters: set[str], response_format: str) -> bool:
    """Whether some legitimate response could match this key.

    For an ordering item that means a *permutation* of the offered parts, not
    merely letters drawn from them. A key of ``"A-B"`` on a three-part item, or
    ``"A-A-B"``, names only real options while being impossible to produce by
    arranging them, so scoring compares every genuine answer against a string
    none of them can equal and the item silently marks everyone wrong.
    """
    if not letters:
        return False
    if response_format == "sequence":
        return sorted(key.split("-")) == sorted(letters)
    return key in letters


def _item_findings(form_code: str, item: Mapping[str, Any]) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    restricted = item["restricted"]
    external_id = restricted["item_id"]
    question = item["question_number"]

    for flag in item.get("teacher_flags", []):
        severity = "blocking" if flag["code"] in BLOCKING_FLAG_CODES else "advisory"
        findings.append(
            PreflightFinding(
                code=flag["code"],
                severity=severity,
                detail=flag.get("detail", ""),
                form_code=form_code,
                question_number=question,
                external_item_id=external_id,
            )
        )

    # A key must name an option that exists, or the item cannot be answered
    # correctly by anyone. Re-checked here so a hand-edited bank cannot bypass
    # the extractor's version of this check.
    letters = {option["letter"] for option in item["safe"]["options"]}
    key = restricted["correct_answer"]
    if not _key_is_answerable(key, letters, item["response_format"]):
        findings.append(
            PreflightFinding(
                code="key_not_in_options",
                severity="blocking",
                detail=f"key {key!r} cannot be produced from options {sorted(letters)}",
                form_code=form_code,
                question_number=question,
                external_item_id=external_id,
            )
        )

    if item["section"] == "listening" and not restricted.get("transcript"):
        findings.append(
            PreflightFinding(
                code="missing_transcript",
                severity="blocking",
                detail=(
                    "a listening item without a script cannot be delivered, "
                    "since approved audio does not exist yet and a proctor "
                    "must be able to read it"
                ),
                form_code=form_code,
                question_number=question,
                external_item_id=external_id,
            )
        )

    return findings


async def import_bank(
    db: AsyncSession,
    bank: Mapping[str, Any],
    *,
    scoring_rule_version: str,
    review_policy: Mapping[str, Any] | None = None,
    source_package: str | None = None,
) -> PlacementTestVersion:
    """Create a ``candidate`` version with its forms, items and keys.

    Idempotent by version code: importing the same bank twice is an error
    rather than a silent duplicate, because two versions with the same code
    would make "which content scored this attempt" unanswerable.

    The version lands as ``candidate``, never ``published``. Publication is a
    separate, gated, audited action.
    """
    version_code = bank["version_code"]

    existing = (
        await db.execute(
            select(PlacementTestVersion).where(
                PlacementTestVersion.version_code == version_code
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise PlacementBankError(
            "VERSION_EXISTS", f"placement version '{version_code}' is already imported"
        )

    keys_payload = [
        {
            "q": item["question_number"],
            "id": item["restricted"]["item_id"],
            "key": item["restricted"]["correct_answer"],
        }
        for form in bank["forms"]
        for item in form["items"]
    ]

    version = PlacementTestVersion(
        version_code=version_code,
        status="candidate",
        blueprint_hash=blueprint_hash(bank),
        scoring_rule_version=scoring_rule_version,
        key_version=_stable_hash(keys_payload)[:16],
        review_policy_version=str((review_policy or {}).get("version", "v1.3-candidate")),
        privacy_policy_version=str(
            bank.get("claim_boundary", {}).get("version", "v1.3")
        ),
        source_package=source_package or bank.get("source_package"),
        duration_minutes=int(bank.get("blueprint", {}).get("duration_minutes", 30)),
        claim_boundary=dict(bank.get("claim_boundary", {})),
        review_policy=dict(review_policy or {}),
    )
    db.add(version)
    await db.flush()

    for form_payload in sorted(bank["forms"], key=lambda f: f["form_code"]):
        form = PlacementForm(
            test_version_id=version.id,
            form_code=form_payload["form_code"],
            item_count=len(form_payload["items"]),
            expected_seconds=sum(
                item["expected_seconds"] for item in form_payload["items"]
            ),
            content_hash=form_content_hash(form_payload),
            key_hash=form_key_hash(form_payload),
            status="active",
        )
        db.add(form)
        await db.flush()

        for item_payload in sorted(
            form_payload["items"], key=lambda i: i["question_number"]
        ):
            safe = item_payload["safe"]
            restricted = item_payload["restricted"]

            item = PlacementItem(
                form_id=form.id,
                question_number=item_payload["question_number"],
                section=item_payload["section"],
                response_format=item_payload["response_format"],
                option_letters=list(item_payload["option_letters"]),
                expected_seconds=item_payload["expected_seconds"],
                audio_playback=item_payload["audio_playback"],
                passage=safe["passage"],
                stem=safe["stem"] or None,
                prompt=safe["prompt"],
                options=list(safe["options"]),
            )
            db.add(item)
            await db.flush()

            db.add(
                PlacementItemKey(
                    item_id=item.id,
                    test_version_id=version.id,
                    external_item_id=restricted["item_id"],
                    slot=restricted["slot"],
                    legacy_band=restricted["legacy_band"],
                    skill=restricted["skill"],
                    item_type=restricted.get("item_type"),
                    topic=restricted.get("topic"),
                    subskill=restricted.get("subskill"),
                    correct_answer=restricted["correct_answer"],
                    answer_text=restricted.get("answer_text"),
                    rationale=restricted.get("rationale"),
                    transcript=restricted.get("transcript"),
                    target_vocabulary=restricted.get("target_vocabulary"),
                    target_grammar=restricted.get("target_grammar"),
                    copyright_status=restricted.get("copyright_status"),
                    qa_status=restricted.get("qa_status"),
                    teacher_review=restricted.get("teacher_review"),
                    teacher_flags=list(item_payload.get("teacher_flags", [])),
                )
            )

    await db.flush()
    return version


async def preflight_version(
    db: AsyncSession, version: PlacementTestVersion
) -> PreflightResult:
    """Re-run the publication gate against what is actually stored.

    Checking the database rather than the source file matters: the file is what
    we meant to import, the rows are what we will actually deliver.
    """
    findings: list[PreflightFinding] = []

    rows = (
        await db.execute(
            select(
                PlacementForm.form_code,
                PlacementItem.question_number,
                PlacementItem.section,
                PlacementItem.option_letters,
                PlacementItem.response_format,
                PlacementItemKey.legacy_band,
                PlacementItemKey.correct_answer,
                PlacementItemKey.external_item_id,
                PlacementItemKey.teacher_flags,
                PlacementItemKey.transcript,
            )
            .join(PlacementItem, PlacementItem.form_id == PlacementForm.id)
            .join(PlacementItemKey, PlacementItemKey.item_id == PlacementItem.id)
            .where(PlacementForm.test_version_id == version.id)
            .order_by(PlacementForm.form_code, PlacementItem.question_number)
        )
    ).all()

    if not rows:
        findings.append(
            PreflightFinding(
                code="no_items", severity="blocking", detail="version has no items"
            )
        )

    by_form: dict[str, list] = {}
    for row in rows:
        by_form.setdefault(row.form_code, []).append(row)

    if len(by_form) != 5:
        findings.append(
            PreflightFinding(
                code="form_count",
                severity="blocking",
                detail=f"expected 5 forms, found {len(by_form)}",
            )
        )

    for form_code, form_rows in sorted(by_form.items()):
        if len(form_rows) != EXPECTED_ITEMS_PER_FORM:
            findings.append(
                PreflightFinding(
                    code="item_count",
                    severity="blocking",
                    detail=f"expected {EXPECTED_ITEMS_PER_FORM} items, found {len(form_rows)}",
                    form_code=form_code,
                )
            )

        sections: dict[str, int] = {}
        bands: dict[int, int] = {}
        for row in form_rows:
            sections[row.section] = sections.get(row.section, 0) + 1
            bands[row.legacy_band] = bands.get(row.legacy_band, 0) + 1

        for section, expected in EXPECTED_SECTIONS.items():
            if sections.get(section, 0) != expected:
                findings.append(
                    PreflightFinding(
                        code="section_blueprint",
                        severity="blocking",
                        detail=f"section {section}: expected {expected}, found {sections.get(section, 0)}",
                        form_code=form_code,
                    )
                )
        for band in range(1, 7):
            if bands.get(band, 0) != EXPECTED_ITEMS_PER_BAND:
                findings.append(
                    PreflightFinding(
                        code="band_blueprint",
                        severity="blocking",
                        detail=f"band {band}: expected {EXPECTED_ITEMS_PER_BAND}, found {bands.get(band, 0)}",
                        form_code=form_code,
                    )
                )

        for row in form_rows:
            letters = set(row.option_letters or [])
            if not _key_is_answerable(
                row.correct_answer, letters, row.response_format
            ):
                findings.append(
                    PreflightFinding(
                        code="key_not_in_options",
                        severity="blocking",
                        detail=(
                            f"key {row.correct_answer!r} cannot be produced "
                            f"from options {sorted(letters)}"
                        ),
                        form_code=form_code,
                        question_number=row.question_number,
                        external_item_id=row.external_item_id,
                    )
                )
            if row.section == "listening" and not row.transcript:
                findings.append(
                    PreflightFinding(
                        code="missing_transcript",
                        severity="blocking",
                        detail="listening item has no script",
                        form_code=form_code,
                        question_number=row.question_number,
                        external_item_id=row.external_item_id,
                    )
                )
            for flag in row.teacher_flags or []:
                findings.append(
                    PreflightFinding(
                        code=flag.get("code", "unknown"),
                        severity=(
                            "blocking"
                            if flag.get("code") in BLOCKING_FLAG_CODES
                            else "advisory"
                        ),
                        detail=flag.get("detail", ""),
                        form_code=form_code,
                        question_number=row.question_number,
                        external_item_id=row.external_item_id,
                    )
                )

    if not (version.claim_boundary or {}).get("purpose"):
        findings.append(
            PreflightFinding(
                code="missing_claim_boundary",
                severity="blocking",
                detail="the learner-facing purpose statement is missing",
            )
        )

    return PreflightResult(version_code=version.version_code, findings=tuple(findings))


async def disputed_item_ids(db: AsyncSession, version_id) -> set:
    """Item UUIDs whose key is disputed, so scoring can exclude them."""
    rows = (
        await db.execute(
            select(PlacementItemKey.item_id, PlacementItemKey.teacher_flags).where(
                PlacementItemKey.test_version_id == version_id
            )
        )
    ).all()
    return {
        row.item_id
        for row in rows
        if any(
            flag.get("code") in BLOCKING_FLAG_CODES for flag in (row.teacher_flags or [])
        )
    }


async def count_items(db: AsyncSession, version_id) -> int:
    return int(
        (
            await db.execute(
                select(func.count(PlacementItem.id))
                .join(PlacementForm, PlacementForm.id == PlacementItem.form_id)
                .where(PlacementForm.test_version_id == version_id)
            )
        ).scalar_one()
    )
