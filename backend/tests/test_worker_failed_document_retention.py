"""A permanently-failed source keeps its bytes in R2.

Production incident, 4 Aug 2026 (course d0311e9b, document f9028fa0): the
worker service carried a revoked OpenRouter key, so every ``process_document``
attempt raised ``AuthenticationError`` at the embedding step. On the third
attempt ``fail_task`` treated the task as permanently failed and deleted the
uploaded PDF from R2, on the premise that

    A permanently-failed doc can't be retried, so the uploaded bytes are
    dead weight.

That premise is false. Two live paths re-download the object after a failure:

  * ``POST /courses/{id}/documents/{doc_id}/reprocess``, the "Retry parsing"
    action the approved setup flow puts beside every failed source, and
  * ``run_parse_syllabus``, the syllabus import job, which downloads the same
    document independently of the processing pipeline.

Both then failed with ``NoSuchKey`` forever, which the UI renders as
``storage_unavailable``: "The file could not be retrieved for processing just
now. Retry in a moment.", inviting a retry that can never succeed against a
file the product itself deleted.

The failure that triggers this is routinely transient or operational (an
expired key, a provider outage, a bad deploy). Destroying the instructor's only
copy turns a fixable config error into unrecoverable data loss, so these tests
pin the inverse: the tombstone is durable, the bytes survive.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from app.models.course import Course
from app.models.document import Document
from app.models.task import Task
from app.models.user import User
from app.services import storage as storage_module
from app.services import worker as worker_module


def _watch_r2_deletes(monkeypatch) -> list[str]:
    """Record every R2 delete, wherever it is issued from.

    Asserted at the S3 client rather than on a module-level name: whichever
    helper a future edit reaches for (``delete_file``, ``delete_file_safe``, a
    raw client call), it lands on ``delete_object`` and this list sees it. A
    test that patched ``worker.delete_file_safe`` would silently stop guarding
    anything the moment that import changed.
    """
    deleted: list[str] = []

    class _RecordingClient:
        def delete_object(self, *, Bucket, Key):  # noqa: N803 - boto3 kwargs
            deleted.append(Key)
            return {}

    monkeypatch.setattr(storage_module, "_s3_client", None, raising=False)
    monkeypatch.setattr(storage_module, "get_s3_client", lambda: _RecordingClient())
    return deleted


async def _make_failed_attempt_task(
    db_session, *, attempts: int, max_attempts: int = 3
) -> tuple[Task, Document]:
    """A ``process_document`` task on its ``attempts``-th try, plus its doc."""
    owner = User(
        better_auth_id=f"ba-{uuid.uuid4()}",
        email=f"teacher-{uuid.uuid4().hex[:8]}@ust.hk",
        full_name="Teacher",
        role="instructor",
    )
    db_session.add(owner)
    await db_session.flush()
    course = Course(
        name="LANG1512",
        code="LANG1512",
        language="english",
        instructor_id=owner.id,
        enroll_code=uuid.uuid4().hex[:8].upper(),
    )
    db_session.add(course)
    await db_session.flush()
    document = Document(
        id=uuid.uuid4(),
        course_id=course.id,
        uploaded_by=owner.id,
        filename="Syllabus.pdf",
        file_type="pdf",
        file_size=1024,
        r2_key="courses/c/documents/d/Syllabus.pdf",
        status="processing",
        kind="syllabus",
    )
    db_session.add(document)
    task = Task(
        task_type="process_document",
        payload={"document_id": str(document.id)},
        status="running",
        attempts=attempts,
        max_attempts=max_attempts,
    )
    db_session.add(task)
    await db_session.commit()
    return task, document


@pytest.mark.asyncio
async def test_permanent_failure_keeps_r2_object(db_session, monkeypatch):
    """The uploaded file survives a permanently-failed processing task.

    This is the regression guard for the incident above: the reprocess
    endpoint and the syllabus import both need these bytes to still exist.
    """
    deleted = _watch_r2_deletes(monkeypatch)

    task, document = await _make_failed_attempt_task(db_session, attempts=3)

    await worker_module.fail_task(
        db_session, task.id, "AuthenticationError", error_code="analysis_unavailable"
    )

    assert deleted == [], (
        "a permanently-failed source must keep its R2 object so Retry parsing "
        f"and the syllabus import can recover; deleted {deleted}"
    )

    refreshed = (
        await db_session.execute(select(Document).where(Document.id == document.id))
    ).scalar_one()
    # The tombstone still has to happen: the user must see 'failed', with a
    # Retry that can actually succeed once the underlying cause is fixed.
    assert refreshed.status == "failed"
    assert refreshed.r2_key == "courses/c/documents/d/Syllabus.pdf"


@pytest.mark.asyncio
async def test_retryable_failure_keeps_r2_object(db_session, monkeypatch):
    """A non-final attempt requeues the task and touches neither doc nor bytes."""
    deleted = _watch_r2_deletes(monkeypatch)

    task, document = await _make_failed_attempt_task(db_session, attempts=1)

    await worker_module.fail_task(db_session, task.id, "transient blip")

    assert deleted == []
    refreshed_task = (
        await db_session.execute(select(Task).where(Task.id == task.id))
    ).scalar_one()
    assert refreshed_task.status == "pending", "attempt 1 of 3 must requeue"

    refreshed_doc = (
        await db_session.execute(select(Document).where(Document.id == document.id))
    ).scalar_one()
    assert refreshed_doc.status == "processing"


@pytest.mark.asyncio
async def test_orphan_reconciler_keeps_r2_object(db_session, monkeypatch):
    """The stuck-document reaper tombstones without destroying the upload.

    Same defect as ``fail_task``, reached by a different route: when the worker
    is SIGKILL'd mid-task the document is left in 'processing' with no live
    task, and this sweep flips it to 'failed'. Deleting the bytes there is
    worse than in ``fail_task``: nothing about the document was even shown to
    be bad, the worker just died, and it leaves Retry parsing permanently
    broken for a file that never got a real attempt.
    """
    deleted = _watch_r2_deletes(monkeypatch)

    _task, document = await _make_failed_attempt_task(db_session, attempts=1)
    # Strand it: 'processing', updated well before the grace window, no live task.
    await db_session.execute(
        text(
            "UPDATE documents SET status='processing', "
            "updated_at = now() - interval '1 hour' WHERE id = :doc_id"
        ),
        {"doc_id": document.id},
    )
    await db_session.execute(
        text("UPDATE tasks SET status='failed' WHERE task_type='process_document'")
    )
    await db_session.commit()

    await worker_module._reconcile_orphaned_documents(db_session)

    assert deleted == [], (
        f"a stranded upload must keep its R2 object; deleted {deleted}"
    )
    # Read columns, not the identity-mapped entity: the sweep is raw SQL, so
    # the ORM copy is stale and refreshing it lazily would need its own IO.
    status, r2_key = (
        await db_session.execute(
            select(Document.status, Document.r2_key).where(
                Document.id == document.id
            )
        )
    ).one()
    assert status == "failed", "the stuck spinner must still be cleared"
    assert r2_key == "courses/c/documents/d/Syllabus.pdf"
