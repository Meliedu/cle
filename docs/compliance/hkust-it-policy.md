# HKUST IT Policy — Meli Compliance Reference

> Status: working reference, not yet actioned. Owner: TBD. Last reviewed: 2026-05-12.
> This file is local-only (`docs/` is gitignored). Mirror it into a shared location once an owning department is assigned.

## Purpose

Meli is an AI language-learning platform for HKUST (web app: Next.js on Vercel + FastAPI on Railway; a mobile app is spec'd but not built). HKUST ITSO publishes mandatory IT policies that govern any app "owned by an HKUST department/unit" or that touches HKUST data/auth. This doc distills those policies against Meli's actual state, flags the gaps, and lays out the order of work. Nothing here should be implemented until we decide which compliance track Meli is on.

### Source pages (all public)

- HKUST Mobile App Policy — `itso.hkust.edu.hk/it-policies-guidelines/hkust-mobile-app-policy`
- Mobile App Security Guideline for Developers — `.../services/cyber-security/mobile-app-security`
- Application Development Guidelines — `.../it-policies-guidelines/application-development`
- Minimum Security Standard (`#application`) — `.../it-policies-guidelines/minimum-security-standard`
- Risk Classification — `.../it-policies-guidelines/risk-classification`
- Central Authentication Server (CAS) — `.../services/cyber-security/authentication-service/sso/cas`

---

## 1. Where Meli sits in HKUST's framework

- **App category (Mobile App Policy):** Meli is an **"HKUST Learning" app** — supports course-related activities for students. Not "Official", not pure "Community". Learning apps get the full lifecycle treatment: Development → Production (compliance check + **CITARS** registration) → Maintenance (re-review every 2 yrs) → Archive.
- **Risk classification:** Meli stores student records, enrollment, learning-performance data (`concept_mastery`, quiz/flashcard attempts) and Canvas OAuth tokens → **High-Risk** under HKUST's Risk Classification ("staff/student records", "learning management systems", systems handling such data). High-Risk pulls in the strictest tier of the Minimum Security Standard.
- **Consequence:** As a High-Risk Learning app, Meli is subject to: CITARS registration, Personal Data Privacy Impact Assessment (PDPIA) + privacy checklist before launch, university auth infra only, API Gateway for HKUST data, vuln scans + source-code scans pre/post deploy, external security review (high-risk apps), and biennial compliance re-checks.

---

## 2. Requirements vs current state

| Policy requirement | Source | Meli today | Gap |
|---|---|---|---|
| Register app in **CITARS** with admin + technical contacts | Mobile App Policy / Mobile App Security | Not registered | **OPEN** — needs an owning department + named contacts |
| Use **university authentication infrastructure only** (CAS / OIDC / OAuth2) | Mobile App Policy / Mobile App Security | Better Auth (self-hosted) IdP + **email/password** (the only live path today). Microsoft Entra ID OAuth is fully wired but **dormant** (`NEXT_PUBLIC_MICROSOFT_SSO_ENABLED=false`, `MICROSOFT_TENANT_ID` already = HKUST tenant) — can't be enabled until Meli has an app registration *inside* the HKUST Entra tenant, or users hit "Need admin approval". Domain-gated to `ust.hk` / `connect.ust.hk`. | **PARTIAL** — email/password as the production path is the part HKUST won't accept. Fix: get the HKUST-tenant Entra app registration done (same ITSO/CITARS step as below), flip the flag on, disable email/password in prod. CAS (`cas.ust.hk` / `castest.ust.hk`) is the alternative if ITSO prefers it. |
| Route HKUST data access through the **HKUST API Gateway** | Mobile App Security | Standalone FastAPI; Canvas calls go direct to `canvas.ust.hk` via per-user OAuth | **OPEN if** we consume any HKUST central APIs. Canvas-via-developer-key may be acceptable; confirm with ITSO. |
| Get **system-owner consent** before accessing existing HKUST data; prefer API tech | Mobile App Policy | Canvas integration uses a single HKUST Canvas developer key | **CHECK** — confirm the Canvas key was issued with proper approval. |
| **PDPIA + privacy checklist** before publishing; handle personal data per HK PDPO | Mobile App Security / App Dev Guidelines | No privacy docs in repo | **OPEN** — produce PDPIA, privacy checklist, and a published privacy notice. Submit to `mobileapps@ust.hk` (mobile) / `seccomp@ust.hk` (general). |
| **External security consultant review** for high-risk apps | Mobile App Security | Internal hardening sprint only (`docs/superpowers/plans/2026-04-16-security-hardening.md`) | **OPEN** — budget/schedule an external pen test before production. |
| Design against **OWASP Top 10 + CWE/SANS**; input validation; remove test data; anti-CSRF | App Dev Guidelines | Pydantic v2 validation, security-headers middleware, nonce CSP, rate limiting; LLM-app hardening in progress | **MOSTLY MET** — finish the hardening sprint; verify no seed/test data ships to prod; document the CSRF posture (token-based JWT in headers ≈ low CSRF surface). |
| **TLS everywhere**, disable old SSL, HTTPS on login + high-risk data pages | App Dev Guidelines / Min Security Std | HSTS (prod), `upgrade-insecure-requests` CSP, Vercel/Railway TLS | **MET** — keep HSTS preload; document. |
| **Patch within 28 days**; keep 3rd-party software updated | Min Security Std (all tiers) | Pinned Docker base digest; deps managed but no documented SLA | **PARTIAL** — adopt a written 28-day patch SLA + Dependabot/Renovate. |
| **Backups** (high-risk) | Min Security Std (high) | Railway-managed Postgres (provider backups), not documented | **PARTIAL** — document/verify backup + restore procedure. |
| **Vulnerability scans pre/post deploy**; **source-code scanning** pre-deploy (high-risk) | Min Security Std (high) | Not in CI | **OPEN** — add SAST (CodeQL/Semgrep) + ITSO Nessus scan before go-live. |
| **Security-by-design from project start** (high-risk) | Min Security Std (high) | Retrofitted via hardening sprint | Acceptable if documented as an ongoing practice. |
| **Maintain IT-resource inventory** via central registration | Min Security Std (all tiers) | None | Folds into CITARS registration above. |
| Compliance re-check **every 2 years**; re-review when programming logic changes | Mobile App Security | n/a | Process item — add to maintenance runbook once registered. |

---

## 3. Already in good shape

- HTTPS/TLS + HSTS (prod), nonce-based CSP, security headers (backend `security_headers.py` + `next.config.ts`).
- Per-user-per-hour rate limiting on `/api/rag/*` with advisory-lock serialization; quota not consumed on errors.
- Pydantic v2 validation at all API boundaries; file-size and parser timeouts capped.
- Secrets via env / Pydantic Settings with production boot-time validation; Canvas tokens encrypted at rest (`INTEGRATIONS_ENCRYPTION_KEY`).
- JWT verification pins EdDSA, validates aud/iss in prod, 30s leeway.
- Domain-gated identity (`ust.hk` instructor / `connect.ust.hk` student), enforced at signup and in the Better Auth `databaseHooks.user.create.before` path (catches SSO sign-ups too).
- Microsoft Entra SSO is the ITSO-preferred path and is already implemented — it just needs the HKUST-tenant app registration to be enabled.

---

## 4. Personal data inventory (feeds the PDPIA)

From `backend/app/models/`:

- **User** (`user.py`): `email`, `full_name`, `avatar_url`, `role`, `better_auth_id` — directly identifying.
- **Enrollments**: course ↔ user ↔ role.
- **Learning artifacts**: `quizzes`, `flashcard_sets`, `revision_sessions`, `pronunciation_scores` — per-user performance.
- **`concept_mastery` / `concept_mastery_history`**: per-user skill estimates + append-only audit log (behavioral profiling — sensitive in a PDPIA sense).
- **`canvas_user_credentials`**: Canvas OAuth access/refresh tokens (encrypted).
- **`api_usage`**: per-user request log (endpoint, method, timestamp).
- Document uploads / RAG chunks: instructor course materials (IP, not personal data, but covers the uploader's consent).

PDPIA must cover: what's collected and why, retention, who can see it (instructors see their course's student progress; students see only their own), **cross-border processing** (Vercel / Railway / OpenRouter / OpenAI / Cloudflare R2 are off-shore — the main PDPO flag), and the deletion/export path (soft-delete `deleted_at` exists; a documented hard-delete/export process for data-subject requests is still missing — `authClient.deleteUser()` + the `beforeDelete` backend hook is the seam to build on).

---

## 5. Action roadmap (in order)

1. **Decide ownership track.** Identify the sponsoring HKUST department/unit and named admin + technical contacts. Blocking, non-technical — CITARS registration and the compliance checks can't start without it.
2. **Talk to ITSO early** (`mobileapps@ust.hk` / `seccomp@ust.hk` / `cchelp@ust.hk`): (a) get an Entra app registration *inside the HKUST tenant* so the already-built Microsoft SSO can be turned on (then disable email/password in prod) — or confirm whether ITSO prefers CAS; (b) confirm whether the current Canvas developer-key flow is approved or needs API-Gateway routing; (c) ask what "high-risk app" external review they require.
3. **Finish the in-flight security hardening sprint** (`docs/superpowers/plans/2026-04-16-security-hardening.md`) — closes most OWASP / LLM-app findings; precondition for any external review.
4. **Write the privacy docs**: PDPIA, privacy checklist, public privacy notice (must disclose off-shore processors), and a documented data-subject access/deletion procedure (extend the existing soft-delete + `deleteUser` hook).
5. **CI security gates**: add SAST (CodeQL or Semgrep) on PRs; request an ITSO Nessus vuln scan against a staging deploy; document a ≤28-day patch SLA + enable Dependabot/Renovate.
6. **Operational docs**: backup/restore runbook (Railway Postgres), incident-response contact, biennial-review reminder, IT-asset inventory entry.
7. **(When the mobile app ships)** re-run this checklist for the iOS/Android build: same CITARS entry, store-listing review (3 working-day SLA from ITSO once docs are in), mobile-specific secure-storage requirements.
8. **Auth changeover** (only after step 2): with the HKUST-tenant Entra app registered, flip `NEXT_PUBLIC_MICROSOFT_SSO_ENABLED=true`, set `MICROSOFT_CLIENT_ID` / `MICROSOFT_CLIENT_SECRET`, and turn off `emailAndPassword` in `frontend/src/lib/auth.ts` for production. If ITSO mandates CAS instead, that's a larger migration (Better Auth tables in the `auth` schema, `users.better_auth_id` linkage, `useApiToken` hook, JWKS verification in `backend/app/services/auth.py`) and gets its own plan. Either way, **do not remove the Microsoft SSO code** until then.

---

## 6. Key files

- `backend/app/services/auth.py` — JWT/JWKS verification; the seam any CAS/OIDC move touches.
- `frontend/src/lib/auth.ts` — Better Auth config: `emailAndPassword`, `socialProviders.microsoft` (dormant), `databaseHooks` domain gate, `deleteUser` hook.
- `frontend/src/lib/auth-domain.ts`, `frontend/src/proxy.ts` — domain gating; CSP/nonce + `login.microsoftonline.com` allowances; session redirect.
- `frontend/src/components/auth/microsoft-button.tsx` + `frontend/src/app/sign-in|sign-up/...` — the dormant SSO UI (gated on `NEXT_PUBLIC_MICROSOFT_SSO_ENABLED`).
- `frontend/.env.local.example` — documents `MICROSOFT_*` vars and why the flag stays `false`.
- `backend/app/middleware/security_headers.py`, `backend/app/middleware/rate_limit.py` — header + rate-limit posture (strong; cite in compliance docs).
- `backend/app/config.py` — secrets validation, Canvas (`canvas.ust.hk`), upload/timeout caps.
- `backend/app/models/` (esp. `user.py`, `score.py`, concept-mastery models, `canvas_user_credentials`) — personal-data inventory for the PDPIA.
- `backend/Dockerfile`, `backend/railway.toml`, `frontend/next.config.ts`, `.vercel/project.json` — deployment surface for backup/patch/CI items.
- `docs/superpowers/plans/2026-04-16-security-hardening.md` — the hardening work to finish first.
- `docs/superpowers/specs/2026-04-26-mobile-app-design.md` (+ related plans) — re-run the checklist when mobile starts.

---

## 7. Definition of done (externally validated, not test-suite validated)

- CITARS entry exists and shows admin + technical contacts.
- ITSO has signed off on the auth model (HKUST-tenant Entra SSO, or CAS) and the Canvas data-access path.
- PDPIA + privacy checklist submitted to `mobileapps@ust.hk` / `seccomp@ust.hk` and acknowledged; privacy notice live on the site.
- External security review completed with findings remediated; ITSO Nessus scan clean (or accepted-risk documented).
- CI shows SAST running on PRs; Dependabot/Renovate active; patch-SLA doc in repo.
- Backup/restore runbook exists and a restore has been test-run once.
- Production sign-in is via HKUST-tenant Entra SSO (or CAS); email/password disabled in prod.
- (Mobile) store-listing approval received from ITSO before public release.
