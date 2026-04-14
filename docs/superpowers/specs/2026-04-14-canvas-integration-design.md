# Canvas Integration — Design Spec

**Date:** 2026-04-14
**Status:** Draft — pending implementation plan
**Scope:** Phase 1 (OAuth 2.0 REST API). Phase 2 (LTI 1.3) deferred.

## 1. Goal

Let HKUST users pull Canvas data into Meli without copy-pasting course codes or re-uploading materials:

- **Student** — pick a course from their Canvas enrollments → auto-enroll in the matching Meli course. No manual enrollment code.
- **Instructor** — pick a course they teach on Canvas → mirror the course into Meli, pull its files, and import the student roster in one flow.

## 2. Non-Goals

- LTI 1.3 launch, Deep Linking, NRPS roster sync, grade passback — Phase 2.
- Canvas Live Events / webhooks — Phase 3+ (requires HKUST Canvas Data Services access).
- Non-HKUST Canvas tenants (`canvas.instructure.com`, other universities) — Phase 2.
- Importing Modules, Pages, Assignments, Announcements — Phase 2 (files only for now).
- Cross-listed course merging (many-to-one mapping) — Phase 2.
- Replacing the existing enrollment-code flow — it coexists as a fallback.

## 3. Decisions (from brainstorming)

| # | Decision | Reason |
|---|---|---|
| 1 | **OAuth 2.0 REST API, not LTI 1.3** (Phase 1) | Matches Meli-first UX ("log into Meli, then pull Canvas"). LTI 1.3 assumes Canvas-first launches. |
| 2 | **Instructor-first course creation** | Student pulls are conditional on instructor having linked a Meli course. Prevents empty orphan courses. |
| 3 | **Pre-provision + optional invite** for non-Meli students | Zero-friction onboarding via Clerk ust.hk SSO; no fragile invite-token flow. |
| 4 | **Manual re-sync + daily scheduled auto-sync** | Roster: auto. Materials: auto-detect, manual ingest (LLM cost gate). Manual "Sync now" button always available. |
| 5 | **Files only** for material import | Matches existing pipeline (parser → chunker → embedder). No new parser logic. |
| 6 | **Role mapping**: Teacher + TA → Instructor; Student → Student; Designer + Observer → skip | Matches course responsibility; avoids Observer leaking student progress. |
| 7a | **Enrollment code coexists** with Canvas flow | Fallback for auditors, TAs, Canvas downtime. |
| 7b | **Disconnect keeps data, stops sync** | Student work preserved. Re-connect dedupes via `canvas_file_id`. |
| 7c | **1:1 course mapping** (enforced by unique constraint) | Simpler data model; cross-listing deferred. |

## 4. Architecture

```
┌──────────────────┐                             ┌──────────────────┐
│   Meli Frontend  │   Clerk SSO (ust.hk)        │  Canvas (HKUST)  │
│   (Next.js)      │                             │  canvas.ust.hk   │
└────────┬─────────┘                             └────────▲─────────┘
         │ Bearer JWT                                     │
         ▼                                                │
┌──────────────────┐      OAuth 2.0 authcode + refresh    │
│   Meli Backend   ├──────────────────────────────────────┘
│   (FastAPI)      │
│                  │      scheduled worker (daily)
│  + CanvasClient  │◄──── polls canvas_integrations
│  + OAuth flows   │      → roster diff + file detection
└──────────────────┘
```

**Three cooperating subsystems, one release:**

1. **Canvas OAuth foundation** — developer key config, per-user credential storage, refresh lifecycle, connect/disconnect API.
2. **Instructor flow** — list taught courses, link → Meli course, import files, import roster.
3. **Student flow** — list enrolled Canvas courses, join Meli courses that their instructor has enabled.

**Key shift from current integration:** tokens move from *per-Meli-course* (`canvas_integrations.access_token_encrypted`) to *per-user* (`canvas_user_credentials`). A user connects Canvas once; every course linkage reuses that credential.

## 5. Data Model

```sql
-- NEW: per-user Canvas credential
CREATE TABLE canvas_user_credentials (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    canvas_base_url VARCHAR(500) NOT NULL,
    canvas_user_id VARCHAR(100) NOT NULL,
    access_token_encrypted VARCHAR(1000) NOT NULL,
    refresh_token_encrypted VARCHAR(1000) NOT NULL,
    access_token_expires_at TIMESTAMPTZ NOT NULL,
    scopes TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',    -- 'active' | 'invalid'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- MODIFY: canvas_integrations (remove per-course token, add ownership + sync timestamps)
-- sync_status column already exists (default 'idle'); Phase 1 uses values 'active' | 'disconnected' | 'error'.
-- Any existing rows were PAT-based and have no OAuth owner; wipe them so the NOT NULL ownership column
-- is safe to add. Affected instructors will be prompted to reconnect via OAuth.
DELETE FROM canvas_integrations;
ALTER TABLE canvas_integrations
    DROP COLUMN access_token_encrypted,
    ADD COLUMN connected_by_user_id UUID NOT NULL REFERENCES users(id),
    ADD COLUMN last_roster_sync_at TIMESTAMPTZ,
    ADD COLUMN last_file_scan_at TIMESTAMPTZ;

-- NEW: pending enrollments for students who haven't signed in to Meli yet
CREATE TABLE pending_enrollments (
    id UUID PRIMARY KEY,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    email VARCHAR(320) NOT NULL,
    canvas_user_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    invited_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (course_id, email)
);

-- MODIFY: documents — track Canvas origin for dedupe
ALTER TABLE documents
    ADD COLUMN canvas_file_id VARCHAR(100),
    ADD COLUMN canvas_file_etag VARCHAR(100);
CREATE UNIQUE INDEX idx_documents_canvas_file
    ON documents (course_id, canvas_file_id)
    WHERE canvas_file_id IS NOT NULL;
```

**Migration:** Existing PAT-based `canvas_integrations` rows get reset — any instructor with an existing integration is prompted to reconnect via OAuth. We drop `access_token_encrypted`, which forces the reconnect. Legacy behaviour is gone; the PAT-based `/connect` endpoint is removed.

## 6. OAuth 2.0 Foundation

### 6.1 Developer Key

Register one Canvas Developer Key with HKUST IT for `canvas.ust.hk`:

- **Redirect URI:** `https://api.meli.hkust.edu/api/canvas/oauth/callback` (prod) and localhost equivalents
- **Scopes** (Canvas-specific URL scopes):
  - `url:GET|/api/v1/users/self`
  - `url:GET|/api/v1/users/self/courses`
  - `url:GET|/api/v1/courses/:id`
  - `url:GET|/api/v1/courses/:id/enrollments`
  - `url:GET|/api/v1/courses/:id/files`
  - `url:GET|/api/v1/files/:id`
  - `url:GET|/api/v1/users/self/enrollments`

Credentials stored in backend env:

```
CANVAS_CLIENT_ID=<from HKUST>
CANVAS_CLIENT_SECRET=<from HKUST>
CANVAS_BASE_URL=https://canvas.ust.hk
CANVAS_REDIRECT_URI=https://api.meli.hkust.edu/api/canvas/oauth/callback
```

### 6.2 Authorization flow

```
1. Frontend → GET /api/canvas/oauth/start
   Backend generates state token (signed JWT with user_id + nonce, 10-min TTL).
   Returns canvas authorize URL:
     https://canvas.ust.hk/login/oauth2/auth
       ?client_id=...&response_type=code
       &redirect_uri=...&state=<jwt>&scope=<space-separated>

2. Frontend redirects user to that URL.

3. Canvas → Meli backend: GET /api/canvas/oauth/callback?code=...&state=...
   Backend:
     - Verifies state JWT, extracts user_id
     - POST canvas/login/oauth2/token with code → receives access_token + refresh_token
     - Fetches /api/v1/users/self to capture canvas_user_id
     - Encrypts tokens (existing app.services.crypto)
     - Upserts canvas_user_credentials row
     - Redirects to frontend /dashboard/canvas?connected=1

4. Frontend shows "Canvas connected" state.
```

### 6.3 Refresh lifecycle

`CanvasClient` is constructed from a `canvas_user_credentials` row. On any 401 response, or when `access_token_expires_at` is within 60 seconds of now, it:

1. POSTs to `canvas.ust.hk/login/oauth2/token` with `grant_type=refresh_token`.
2. Updates the row with new access token + expiry (refresh token stays the same per Canvas docs).
3. Retries the original request once.

If refresh fails with 4xx, the credential row is marked `invalid` (add `status` column in migration: `'active' | 'invalid'`) and the user is asked to reconnect next time they open Canvas features.

### 6.4 Disconnect

`DELETE /api/canvas/connection`:
1. Deletes the `canvas_user_credentials` row.
2. For every `canvas_integrations` where `connected_by_user_id == user.id`, mark sync status `'disconnected'` (stops the scheduled worker but leaves data intact).
3. Re-connecting later: on first sync, resumes; dedupe via `canvas_file_id` prevents document duplication.

## 7. Instructor Flow

### 7.1 List taught courses

`GET /api/canvas/courses?role=teacher`:

- Uses caller's `canvas_user_credentials`.
- Calls `/api/v1/users/self/courses?enrollment_type=teacher&enrollment_type=ta&state[]=available`.
- Returns `[{canvas_course_id, name, course_code, term, already_linked_meli_course_id | null}]`.

### 7.2 Link a Canvas course → Meli course

`POST /api/canvas/courses/{canvas_course_id}/link`:

- Verifies caller is Teacher or TA on that Canvas course (refetch enrollment for safety).
- If `canvas_integrations` already exists for that (canvas_base_url, canvas_course_id) → 409 "already linked".
- Creates a new Meli `courses` row (name + code copied from Canvas).
- Creates `canvas_integrations` row with `connected_by_user_id = user.id` and `sync_status = 'active'`.
- Auto-enrolls the caller as Instructor.
- Returns the Meli course id.

### 7.3 Import files

Two endpoints:

**`GET /api/courses/{course_id}/canvas/files`** — list files available to import. Returns both:
- `already_imported`: files whose `canvas_file_id` exists in `documents`
- `available`: files not yet imported

**`POST /api/courses/{course_id}/canvas/files/import`** with `{file_ids: [...]}`:

Replaces the current `501 Not Implemented` stub. For each selected Canvas file:

1. Fetch file metadata from `/api/v1/files/:id` (gets signed download URL + size + content-type).
2. Validate content-type against `settings.allowed_document_types`.
3. Stream-download from Canvas → upload to R2 (reuses `app.services.storage`).
4. Create `documents` row with `canvas_file_id`, `canvas_file_etag`, `status='pending'`.
5. Enqueue a processing task in the existing `tasks` table (picked up by `worker.py` — parse → chunk → embed).

Dedupe: the unique index on `(course_id, canvas_file_id)` prevents double-import. Re-import shows as a no-op; updated files (different etag) are Phase 2.

### 7.4 Import roster

`POST /api/courses/{course_id}/canvas/roster/import` with `{send_invite_emails: bool}`:

1. Verify caller is instructor on that Meli course.
2. `CanvasClient.list_enrollments(canvas_course_id)` → paginated.
3. Filter to Teacher, TA, Student roles (skip Designer, Observer).
4. For each enrollment, compute target Meli role (Teacher/TA → Instructor; Student → Student).
5. Match against `users` table by `email` (Canvas's `login_id` or `email` field — prefer `login_id` which is ust.hk / connect.ust.hk SIS login).
6. For each match → upsert `enrollments(course_id, user_id, role)`.
7. For each miss → upsert `pending_enrollments(course_id, email, canvas_user_id, role, invited_at=now() if send_invite_emails else null)`.
8. Compute a diff against current enrollments: anyone in Meli but missing from Canvas → soft-unenroll (set `enrollments.deleted_at = now()`). Preserves quiz attempts, flashcard progress, etc.
9. Return diff summary: `{added: N, unchanged: M, dropped: K, pending: P}`.
10. If `send_invite_emails`: enqueue an email task per pending row (one-shot, idempotent via `invited_at`).

### 7.5 Clerk sign-in hook claims pending enrollments

Extend existing Clerk JWT verification in `app.api.deps.get_current_user`:

After a user is auto-created on first login, run:

```python
pending = await db.execute(
    select(PendingEnrollment).where(PendingEnrollment.email == user.email)
)
for row in pending.scalars():
    db.add(Enrollment(course_id=row.course_id, user_id=user.id, role=row.role))
    await db.delete(row)
```

Wrapped in the same transaction as user creation to keep it atomic.

## 8. Student Flow

### 8.1 List enrolled Canvas courses with Meli availability

`GET /api/canvas/courses?role=student`:

- Calls `/api/v1/users/self/courses?enrollment_type=student&state[]=available`.
- For each result, check `canvas_integrations` for an existing linkage:
  ```python
  canvas_integrations.join(courses, ...).filter(
      canvas_course_id == canvas_id,
      canvas_base_url == "https://canvas.ust.hk",
      sync_status != "disconnected",
  )
  ```
- Returns `[{canvas_course_id, name, course_code, meli_course_id | null, already_enrolled: bool}]`.
- UI shows each course with one of three states: "Join Meli course", "Already in Meli", "Instructor hasn't enabled Meli".

### 8.2 Join a Meli course from Canvas

`POST /api/canvas/courses/{canvas_course_id}/join`:

1. Fetch caller's Canvas enrollments, confirm they are a student on that course.
2. Find `canvas_integrations` row for that Canvas course; if none → 404 "Instructor hasn't enabled Meli for this course."
3. Upsert `enrollments(course_id=meli_course_id, user_id=user.id, role='student')`.
4. If a `pending_enrollments` row existed (rare race), delete it.
5. Return the Meli course id.

## 9. Sync Worker

A new daily job added to the existing `worker.py` loop (or a sibling task scheduler — spec'd in the implementation plan):

**Trigger:** once per day per `canvas_integrations` row where `sync_status == 'active'` and `connected_by_user_id` has a valid credential.

**For each integration:**

1. **Roster diff** (cheap):
   - Fetch current Canvas enrollments.
   - Compute add/drop diff against `enrollments` + `pending_enrollments`.
   - Apply: auto-enroll matched users, pre-provision unmatched, soft-unenroll drops.
   - Update `last_roster_sync_at`.
   - Record diff to a new `canvas_sync_events` table (for the notification digest).

2. **File detection** (cheaper — no download):
   - Fetch current Canvas file list.
   - Compute list of files not yet in `documents` (by `canvas_file_id`).
   - Store count on the integration row; UI surfaces "2 new files available to import".
   - Do NOT download or ingest — instructor must click to import (LLM cost gate).
   - Update `last_file_scan_at`.

3. **Failure handling:**
   - 401/403 → mark credential `invalid`, notify instructor on next login.
   - 429 (rate limit) → backoff; retry next day.
   - 5xx → log + retry next day.

**Manual override:** `POST /api/courses/{course_id}/canvas/sync` triggers the same logic on demand for one course (ignores last_sync_at gating).

**Notification digest:** `GET /api/courses/{course_id}/canvas/sync-events` returns the last N events so the frontend can show "Since last visit: 3 new students, 1 dropped, 2 new files."

## 10. Security

- **Token encryption** — reuses `app.services.crypto.encrypt_secret` (already AES-based with key from env).
- **State parameter** — signed JWT with user_id + nonce + 10-min TTL; prevents CSRF on the OAuth callback.
- **URL safety** — existing `validate_canvas_base_url` keeps working; Phase 1 hard-codes `canvas.ust.hk` via env, so the allowlist is a single entry.
- **Role authorization** — `require_instructor` guards all link/import endpoints. Student endpoints use `get_current_user`.
- **Email-based matching** — matched exclusively against ust.hk / connect.ust.hk domains (reuse `ALLOWED_EMAIL_DOMAINS`). Off-domain emails in a Canvas roster are skipped with a warning in the diff.
- **Rate limiting** — the Canvas-facing endpoints are not billed LLM calls, so they sit outside `/api/rag/*` and are rate-limited by nginx / Railway defaults. Import endpoints get a per-user per-minute cap (20/min) to prevent abuse.

## 11. Error handling

| Condition | Response |
|---|---|
| User hasn't connected Canvas | 409 with `code=canvas_not_connected`; frontend shows "Connect Canvas" CTA |
| Credential expired + refresh failed | 401 with `code=canvas_reauth_required`; frontend re-runs OAuth flow |
| Canvas 429 | Return 503 with `Retry-After`; frontend shows toast |
| Canvas 5xx | 502 with correlation id; logged |
| Import of already-imported file | Silently no-op, returned in the "already_imported" bucket |
| Non-HKUST email in roster | Logged + included in diff as `skipped_off_domain` |

## 12. Frontend Surfaces

New surfaces (implementation plan will specify exact component structure):

- **`/dashboard/canvas`** — account-level Canvas connection settings (connect / disconnect, show connected email, show last sync).
- **Course creation wizard** — new "Import from Canvas" path alongside the current manual create. Instructor picks from their Canvas taught-courses list.
- **Course settings → Canvas tab** — shows linked Canvas course; file import picker; roster import button; sync history.
- **Student course join page** — extended to show Canvas enrollments section above the current enrollment-code input. Each Canvas course is "Join", "Already enrolled", or "Not yet enabled".

## 13. Testing

- **Unit:** OAuth callback state verification, refresh-on-401 logic, role mapping, diff computation, pending-enrollment claim at login.
- **Integration:** mock Canvas API with `httpx.MockTransport`; cover full OAuth flow, file import happy path + dedupe, roster import matching + pre-provisioning, drop detection.
- **E2E:** Playwright test — student clicks "Connect Canvas" (OAuth mocked), picks course, lands enrolled in Meli. Instructor clicks "Link Canvas course," imports 2 files, imports roster with 1 matched + 1 pending student.
- **Coverage target:** 80% on new backend services (`canvas_oauth.py`, `canvas_sync.py`), 80% on new frontend hooks.

## 14. Open questions for the implementation plan

- Exact placement of the scheduled sync (extend `worker.py` vs. a separate scheduler like APScheduler or Railway cron).
- Whether to chunk the files-list endpoint (Canvas paginates at 50; instructor courses can have >200 files).
- Whether invite emails use an existing transactional provider (Meli currently has none wired — may need Resend/Postmark setup, or defer emails to Phase 1.1).

## 15. Rollout

1. Register HKUST Canvas Developer Key — blocking external dependency; request before coding starts.
2. Ship migrations + OAuth foundation (no user-facing feature yet).
3. Ship instructor flow (link + file import + roster import).
4. Ship student flow.
5. Ship daily sync worker.
6. Remove old PAT-based `/connect` endpoint.
