# P0 — Shell & Foundations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the pilot-config module, role-scoped app shells (`/teacher`, `/student`), backend-authoritative roles, P0 pattern components, and the OIDC-ready sign-in rebuild — the foundation every later phase builds on.

**Architecture:** Backend gains a typed `PilotProfile` registry exposed at `GET /api/config`. Frontend gains two role-gated route trees whose layouts reuse the existing dashboard shell components, a `useRole` backed by `GET /api/auth/me`, and a `patterns/` component tier. Better Auth gains dormant `genericOAuth` slots for the two HKUST Entra tenants.

**Tech Stack:** FastAPI + Pydantic v2 + pytest; Next.js 16 App Router + React 19 + TanStack Query + next-intl + Playwright; Better Auth `genericOAuth`.

**Context for a fresh session:** Read `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` (Global Rules) and spec §3 first. Figma: pull group `1372:6` (teacher) and `1372:226` (student) via `get_metadata`, then `get_design_context` per screen before UI tasks. Read `frontend/AGENTS.md` and relevant `node_modules/next/dist/docs/` pages before frontend work. Backend tests need the `langassistant_test` DB and run from `backend/` with `pytest`.

---

### Task 1: PilotProfile schema + CLE profile

**Files:**
- Create: `backend/app/pilot/__init__.py`, `backend/app/pilot/base.py`, `backend/app/pilot/cle.py`
- Test: `backend/tests/test_pilot_config.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_pilot_config.py
import pytest
from pydantic import ValidationError


def test_cle_profile_is_valid_and_complete():
    from app.pilot import get_pilot_profile

    profile = get_pilot_profile()
    assert profile.id == "cle"
    assert profile.institution == "HKUST CLE"
    # trust-language essentials the frontend depends on
    assert profile.confidence_scale.min == -2
    assert profile.confidence_scale.max == 2
    assert set(profile.confidence_scale.labels) == {-2, -1, 0, 1, 2}
    assert "reading" in profile.skill_taxonomy
    assert "pronunciation" in profile.skill_taxonomy
    assert profile.terminology["checkpoint"] == "Checkpoint"
    assert profile.role_rules["ust.hk"] == "instructor"
    assert profile.role_rules["connect.ust.hk"] == "student"
    assert profile.report_cadence.weekly is True
    assert profile.report_cadence.end_term is True
    assert len(profile.score_category_defaults) >= 1
    # readiness definitions exist for the P2 join funnel
    phases = {p.phase for p in profile.readiness}
    assert {"eligibility_survey", "ready_check"} <= phases
    for phase in profile.readiness:
        assert len(phase.questions) >= 1
    # claim limits: recommendation copy must exist (doc §8.2 claim discipline)
    assert "recommendation" in profile.claim_limits


def test_unknown_profile_raises():
    from app.pilot import load_profile

    with pytest.raises(RuntimeError, match="Unknown PILOT_PROFILE"):
        load_profile("nonexistent")
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `backend/`): `pytest tests/test_pilot_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.pilot'`

- [ ] **Step 3: Implement the schema**

```python
# backend/app/pilot/base.py
"""Typed pilot profile: everything institution-specific lives here, not in code."""
from typing import Literal

from pydantic import BaseModel, Field


class ConfidenceScale(BaseModel):
    min: int
    max: int
    labels: dict[int, str]


class ScoreCategoryDefault(BaseModel):
    name: str
    weight: float | None = None


class ReadinessQuestion(BaseModel):
    id: str
    kind: Literal["single_choice", "multi_choice", "scale", "short_text"]
    prompt: str
    options: list[str] = Field(default_factory=list)


class ReadinessPhaseDef(BaseModel):
    phase: Literal["eligibility_survey", "ready_check", "diagnostic"]
    title: str
    intro: str
    questions: list[ReadinessQuestion]


class ReportCadence(BaseModel):
    weekly: bool
    end_term: bool


class PilotProfile(BaseModel):
    id: str
    institution: str
    course_family: str
    terminology: dict[str, str]
    skill_taxonomy: list[str]
    confidence_scale: ConfidenceScale
    score_category_defaults: list[ScoreCategoryDefault]
    readiness: list[ReadinessPhaseDef]
    report_cadence: ReportCadence
    role_rules: dict[str, str]  # email domain -> role
    locales: list[str]
    claim_limits: dict[str, str]  # context key -> student-facing limit copy
```

```python
# backend/app/pilot/cle.py
"""HKUST CLE pilot configuration (LANG1511-1515). Values from the CLE Pilot
Service Report; wording changes go here, never into components/services."""
from app.pilot.base import (
    ConfidenceScale,
    PilotProfile,
    ReadinessPhaseDef,
    ReadinessQuestion,
    ReportCadence,
    ScoreCategoryDefault,
)

CLE_PROFILE = PilotProfile(
    id="cle",
    institution="HKUST CLE",
    course_family="Chinese language courses (LANG1511-LANG1515)",
    terminology={
        "checkpoint": "Checkpoint",
        "session": "Session",
        "ilo": "ILO",
        "practice": "Practice",
        "activity": "Activity",
        "follow_up": "Follow-up",
        "course_memory": "Course Memory",
    },
    skill_taxonomy=[
        "reading", "speaking", "listening", "writing",
        "vocabulary", "grammar", "pronunciation", "task_comprehension",
    ],
    confidence_scale=ConfidenceScale(
        min=-2, max=2,
        labels={
            -2: "Not familiar at all", -1: "Heard of it, unsure",
            0: "Somewhat understand", 1: "Understand well",
            2: "Could explain it to someone",
        },
    ),
    score_category_defaults=[
        ScoreCategoryDefault(name="Participation", weight=None),
        ScoreCategoryDefault(name="Quizzes", weight=None),
    ],
    readiness=[
        ReadinessPhaseDef(
            phase="eligibility_survey",
            title="Course Interest & Background",
            intro="A few short questions about your background with Chinese. This helps frame the course — it is not a test.",
            questions=[
                ReadinessQuestion(id="prior_study", kind="single_choice",
                    prompt="How long have you studied Chinese before?",
                    options=["Never", "Under 1 year", "1-3 years", "3+ years"]),
                ReadinessQuestion(id="goals", kind="multi_choice",
                    prompt="What do you most want from this course?",
                    options=["Everyday conversation", "Reading & writing", "Pronunciation", "Academic/work use"]),
            ],
        ),
        ReadinessPhaseDef(
            phase="ready_check",
            title="Ready Check",
            intro="Rate your confidence with these areas. Honest answers give you a more useful starting point.",
            questions=[
                ReadinessQuestion(id="conf_listening", kind="scale", prompt="Understanding spoken Mandarin"),
                ReadinessQuestion(id="conf_speaking", kind="scale", prompt="Speaking in everyday situations"),
                ReadinessQuestion(id="conf_reading", kind="scale", prompt="Reading simple passages"),
                ReadinessQuestion(id="conf_writing", kind="scale", prompt="Writing characters and short sentences"),
            ],
        ),
    ],
    report_cadence=ReportCadence(weekly=True, end_term=True),
    role_rules={"ust.hk": "instructor", "connect.ust.hk": "student"},
    locales=["en", "zh-Hant"],
    claim_limits={
        "recommendation": "This is guidance based on your survey answers, not a placement decision. Your instructor and the CLE make final course decisions.",
        "learning_profile": "This profile describes patterns in the course work you completed. It is not a judgment of your ability or identity.",
        "report": "This report summarizes reviewed course evidence. It describes observed participation and learning patterns only.",
    },
)
```

```python
# backend/app/pilot/__init__.py
from functools import lru_cache

from app.config import settings
from app.pilot.base import PilotProfile
from app.pilot.cle import CLE_PROFILE

_REGISTRY: dict[str, PilotProfile] = {"cle": CLE_PROFILE}


def load_profile(profile_id: str) -> PilotProfile:
    try:
        return _REGISTRY[profile_id]
    except KeyError as exc:
        raise RuntimeError(
            f"Unknown PILOT_PROFILE '{profile_id}'. Known: {sorted(_REGISTRY)}"
        ) from exc


@lru_cache(maxsize=1)
def get_pilot_profile() -> PilotProfile:
    return load_profile(settings.pilot_profile)
```

- [ ] **Step 4: Add the setting** — in `backend/app/config.py`, inside `class Settings`, add (match the file's existing field style):

```python
    pilot_profile: str = "cle"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_pilot_config.py -v` → Expected: 2 passed

- [ ] **Step 6: Startup validation** — in `backend/app/main.py` lifespan (before worker startup), add a fail-fast line + note: `get_pilot_profile()` (import from `app.pilot`). Unknown profile now crashes boot instead of failing at request time. Run the full quick check: `pytest tests/test_pilot_config.py tests/test_config_validation.py -v` → passes.

- [ ] **Step 7: Commit**

```bash
git add backend/app/pilot backend/app/config.py backend/app/main.py backend/tests/test_pilot_config.py
git commit -m "feat(pilot): typed pilot profile registry with CLE configuration"
```

---

### Task 2: GET /api/config endpoint

**Files:**
- Create: `backend/app/api/config.py`
- Modify: `backend/app/api/__init__.py` (import + `include_router`)
- Test: `backend/tests/test_config_endpoint.py`

- [ ] **Step 1: Write the failing test** (use existing fixtures from `conftest.py`; copy the auth pattern from `backend/tests/test_api_auth*.py` / any authed endpoint test — check how `async_client` + logged-in user fixtures are named there and match it)

```python
# backend/tests/test_config_endpoint.py
import pytest


@pytest.mark.asyncio
async def test_config_returns_pilot_profile(async_client, logged_in_user):
    resp = await async_client.get("/api/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["id"] == "cle"
    assert data["confidence_scale"]["min"] == -2
    assert "terminology" in data and "skill_taxonomy" in data


@pytest.mark.asyncio
async def test_config_requires_auth(async_client):
    resp = await async_client.get("/api/config")
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run to verify FAIL** — `pytest tests/test_config_endpoint.py -v` → 404s.

- [ ] **Step 3: Implement the router** (match the envelope import used by `app/api/auth.py` — likely `from app.schemas.common import APIResponse`; verify and use the same)

```python
# backend/app/api/config.py
"""Read-only pilot configuration for the frontend (terminology, taxonomy,
confidence scale, readiness definitions, claim-limit copy)."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.pilot import get_pilot_profile
from app.pilot.base import PilotProfile
from app.schemas.common import APIResponse

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=APIResponse[PilotProfile])
async def get_config(
    _user: User = Depends(get_current_user),
) -> APIResponse[PilotProfile]:
    return APIResponse(success=True, data=get_pilot_profile())
```

Register in `backend/app/api/__init__.py`: `from app.api.config import router as config_router` + `api_router.include_router(config_router)`.

- [ ] **Step 4: Run to verify PASS** — `pytest tests/test_config_endpoint.py -v` → 2 passed.

- [ ] **Step 5: Commit** — `git add backend/app/api && git commit -m "feat(pilot): GET /api/config exposes the pilot profile"`

---

### Task 3: Backend-authoritative useRole

The current `frontend/src/hooks/use-role.ts` guesses role from the email domain client-side. Replace with the backend's `users.role` via `GET /api/auth/me` (endpoint exists in `backend/app/api/auth.py`).

**Files:**
- Modify: `frontend/src/hooks/use-role.ts`
- Read first: `frontend/src/lib/api.ts` (how `apiFetch` builds paths/token), `frontend/src/hooks/use-auth.ts`, `backend/app/api/auth.py` (response shape)

- [ ] **Step 1: Rewrite the hook**

```typescript
// frontend/src/hooks/use-role.ts
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import { useApiToken } from "@/hooks/use-api-token";

type Role = "instructor" | "student";

interface MeResponse {
  id: string;
  email: string;
  role: Role;
  full_name?: string | null;
}

export function useRole() {
  const { getToken, isReady } = useApiToken(); // match the real hook API in use-api-token.ts
  const { data, isPending } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => apiFetch<MeResponse>("/auth/me", { getToken }), // match apiFetch's real signature
    enabled: isReady,
    staleTime: 5 * 60 * 1000,
  });

  const role: Role | null = data?.role ?? null;
  return {
    role,
    isInstructor: role === "instructor",
    isStudent: role === "student",
    isLoaded: !isPending && role !== null,
  } as const;
}
```

**Adapt the token/fetch wiring to the actual signatures** in `use-api-token.ts` / `api.ts` — other hooks in `frontend/src/hooks/` show the established call pattern; copy it exactly. Keep the returned shape `{ role, isInstructor, isStudent, isLoaded }` — existing callers depend on it.

- [ ] **Step 2: Verify** — `cd frontend && npx tsc --noEmit && npm run lint` → clean. Grep all `useRole()` call sites (`Grep: useRole\(`) and confirm none read removed fields.

- [ ] **Step 3: Commit** — `git commit -am "fix(auth): role comes from backend users.role, not email-domain guess"`

---

### Task 4: Pilot config on the frontend

**Files:**
- Create: `frontend/src/lib/pilot-config.ts`, `frontend/src/hooks/use-pilot-config.ts`

- [ ] **Step 1: Types + hook**

```typescript
// frontend/src/lib/pilot-config.ts
export interface ConfidenceScale {
  min: number;
  max: number;
  labels: Record<string, string>;
}

export interface ReadinessQuestion {
  id: string;
  kind: "single_choice" | "multi_choice" | "scale" | "short_text";
  prompt: string;
  options: string[];
}

export interface ReadinessPhaseDef {
  phase: "eligibility_survey" | "ready_check" | "diagnostic";
  title: string;
  intro: string;
  questions: ReadinessQuestion[];
}

export interface PilotConfig {
  id: string;
  institution: string;
  course_family: string;
  terminology: Record<string, string>;
  skill_taxonomy: string[];
  confidence_scale: ConfidenceScale;
  score_category_defaults: { name: string; weight: number | null }[];
  readiness: ReadinessPhaseDef[];
  report_cadence: { weekly: boolean; end_term: boolean };
  locales: string[];
  claim_limits: Record<string, string>;
}
```

```typescript
// frontend/src/hooks/use-pilot-config.ts
"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { PilotConfig } from "@/lib/pilot-config";

// Same token wiring as use-role.ts (Task 3) — copy that exact pattern.
export function usePilotConfig() {
  /* useQuery({ queryKey: ["pilot-config"], queryFn: () => apiFetch<PilotConfig>("/config", ...), staleTime: Infinity }) */
}
```

Fill the hook body identically to Task 3's query wiring (`staleTime: Infinity` — config is static per deployment). Export `{ config, isLoaded }`.

- [ ] **Step 2: Verify** — `npx tsc --noEmit` clean.
- [ ] **Step 3: Commit** — `git commit -am "feat(pilot): frontend pilot-config types + hook"`

---

### Task 5: P0 pattern components (PageHeader, StateBanner, EmptyState)

**Files:**
- Create: `frontend/src/components/patterns/page-header.tsx`, `frontend/src/components/patterns/state-banner.tsx`, `frontend/src/components/patterns/empty-state.tsx`, `frontend/src/components/patterns/index.ts`
- Modify: `frontend/messages/en.json` (add `patterns.*` keys used below)

Design rules: tokens only (`var(--color-*)`, `--space-*`, `--radius-*`, `--text-*`); one visual treatment per semantic tone; every state shows a reason and (optionally) a next action. Invoke `frontend-design:frontend-design` before styling.

- [ ] **Step 1: PageHeader**

```tsx
// frontend/src/components/patterns/page-header.tsx
import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  breadcrumb?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, description, breadcrumb, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      {breadcrumb ? <div className="page-header__breadcrumb">{breadcrumb}</div> : null}
      <div className="page-header__row">
        <div>
          <h1 className="page-header__title">{title}</h1>
          {description ? <p className="page-header__description">{description}</p> : null}
        </div>
        {actions ? <div className="page-header__actions">{actions}</div> : null}
      </div>
    </header>
  );
}
```

Use the codebase's actual styling idiom — check two existing components in `components/dashboard/` first: if they use Tailwind classes, convert the classNames above to Tailwind utilities referencing token-backed theme values; if CSS modules, follow that. Do NOT introduce a new styling system.

- [ ] **Step 2: StateBanner** — semantic tones `info | waiting | warning | blocked | success`, icon + reason + optional action slot:

```tsx
// frontend/src/components/patterns/state-banner.tsx
import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Clock, Info, Lock } from "lucide-react";

type Tone = "info" | "waiting" | "warning" | "blocked" | "success";

const TONE_ICON: Record<Tone, typeof Info> = {
  info: Info, waiting: Clock, warning: AlertTriangle, blocked: Lock, success: CheckCircle2,
};

interface StateBannerProps {
  tone: Tone;
  title: string;
  reason?: string;
  action?: ReactNode;
}

export function StateBanner({ tone, title, reason, action }: StateBannerProps) {
  const Icon = TONE_ICON[tone];
  return (
    <div role="status" data-tone={tone} className="state-banner">
      <Icon aria-hidden className="state-banner__icon" />
      <div className="state-banner__body">
        <p className="state-banner__title">{title}</p>
        {reason ? <p className="state-banner__reason">{reason}</p> : null}
      </div>
      {action ? <div className="state-banner__action">{action}</div> : null}
    </div>
  );
}
```

Tone→token mapping: info→accent, waiting→sand/gold, warning→warning, blocked→error-muted, success→success. Same styling-idiom rule as Step 1.

- [ ] **Step 3: EmptyState** — centered illustration-slot + title + reason + optional CTA; `variant="empty" | "waiting"` (waiting adds the Clock icon and calmer copy tone). Same prop discipline: `{ variant, title, reason, action?, icon? }`. Implement analogously to StateBanner (full component, ~40 lines).

- [ ] **Step 4: Barrel + i18n** — `patterns/index.ts` re-exports all three. Add generic keys to `messages/en.json` under `patterns` (e.g. `patterns.waiting.title`). Verify `npx tsc --noEmit && npm run lint`.

- [ ] **Step 5: Commit** — `git commit -am "feat(ui): P0 pattern components (PageHeader, StateBanner, EmptyState)"`

---

### Task 6: Role-scoped route trees + RoleGate + dashboard redirect

**Files:**
- Create: `frontend/src/components/layout/role-gate.tsx`, `frontend/src/app/(app)/teacher/layout.tsx`, `frontend/src/app/(app)/teacher/dashboard/page.tsx`, `frontend/src/app/(app)/teacher/courses/page.tsx`, `frontend/src/app/(app)/teacher/calendar/page.tsx`, `frontend/src/app/(app)/teacher/insights/page.tsx`, `frontend/src/app/(app)/student/layout.tsx`, `frontend/src/app/(app)/student/dashboard/page.tsx`, `frontend/src/app/(app)/student/courses/page.tsx`, `frontend/src/app/(app)/student/calendar/page.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx` (role redirect)
- Read first: `frontend/src/app/dashboard/layout.tsx` + `components/layout/` (reuse the shell), `frontend/src/app/dashboard/page.tsx` + `components/dashboard/` (reuse content)

- [ ] **Step 1: RoleGate**

```tsx
// frontend/src/components/layout/role-gate.tsx
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useRole } from "@/hooks/use-role";

interface RoleGateProps {
  allow: "instructor" | "student";
  children: React.ReactNode;
}

/** UI-lane guard only — data access is enforced by the backend on every endpoint. */
export function RoleGate({ allow, children }: RoleGateProps) {
  const { role, isLoaded } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded && role !== allow) {
      router.replace(role === "instructor" ? "/teacher/dashboard" : "/student/dashboard");
    }
  }, [isLoaded, role, allow, router]);

  if (!isLoaded || role !== allow) return null; // brief blank beats flashing the wrong lane
  return <>{children}</>;
}
```

- [ ] **Step 2: Layouts** — each layout wraps children in the existing dashboard shell component (found in Step "read first") + `RoleGate`, passing the role's nav config (Task 7). Teacher layout: `allow="instructor"`; student: `allow="student"`.

- [ ] **Step 3: Pages** — `teacher/dashboard` and `student/dashboard` compose the SAME components the current `/dashboard/page.tsx` renders (import them; do not copy-paste JSX bodies — extract shared section components if the current page has inline JSX). `*/courses` reuse the existing course-list page content. `*/calendar`: PageHeader + existing mini-calendar + upcoming list + `StateBanner tone="info"` noting full calendar arrives in P4. `teacher/insights`: PageHeader + `EmptyState variant="waiting"` ("No evidence yet" — designed per T086/S071 spirit; full build in P6).

- [ ] **Step 4: /dashboard redirect**

```tsx
// frontend/src/app/dashboard/page.tsx  (replace file contents)
"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useRole } from "@/hooks/use-role";

export default function DashboardRedirect() {
  const { role, isLoaded } = useRole();
  const router = useRouter();

  useEffect(() => {
    if (isLoaded) {
      router.replace(role === "instructor" ? "/teacher/dashboard" : "/student/dashboard");
    }
  }, [isLoaded, role, router]);

  return null;
}
```

Legacy subroutes (`/dashboard/courses/[courseId]/...`) stay untouched — later phases replace them.

- [ ] **Step 5: Verify** — `npm run dev`, sign in as an instructor seed user → lands on `/teacher/dashboard`; manually visit `/student/dashboard` → bounced back. Repeat inverted for a student user. `npx tsc --noEmit` clean.

- [ ] **Step 6: Commit** — `git commit -am "feat(shell): role-scoped /teacher and /student route trees with RoleGate"`

---

### Task 7: Nav config + sidebar per Figma (T003/T004, S014/S015)

**Files:**
- Create: `frontend/src/components/layout/nav-config.ts`
- Modify: the existing sidebar component in `frontend/src/components/layout/` (accept a `NavItem[]` prop; add collapsed mode if missing)
- Figma: pull `get_design_context` for T003 (`1372:12`), T004 (`1372:14`), S014 (`1372:228`), S015 (`1372:230`) first.

- [ ] **Step 1: Nav config**

```typescript
// frontend/src/components/layout/nav-config.ts
import {
  BarChart3, BookOpen, Calendar, GraduationCap, LayoutDashboard,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  labelKey: string; // next-intl key under nav.*
  href: string;
  icon: LucideIcon;
}

export const TEACHER_NAV: NavItem[] = [
  { labelKey: "nav.dashboard", href: "/teacher/dashboard", icon: LayoutDashboard },
  { labelKey: "nav.courses", href: "/teacher/courses", icon: BookOpen },
  { labelKey: "nav.calendar", href: "/teacher/calendar", icon: Calendar },
  { labelKey: "nav.insights", href: "/teacher/insights", icon: BarChart3 },
];

export const STUDENT_NAV: NavItem[] = [
  { labelKey: "nav.dashboard", href: "/student/dashboard", icon: LayoutDashboard },
  { labelKey: "nav.courses", href: "/student/courses", icon: GraduationCap },
  { labelKey: "nav.calendar", href: "/student/calendar", icon: Calendar },
];
```

- [ ] **Step 2: Sidebar** — refactor the existing sidebar to render from `NavItem[]` (keep the rail tokens `--color-rail*`), add collapse toggle persisting to `localStorage` (`meli.sidebar.collapsed`), active-route highlight via `usePathname()`. Add `nav.*` keys to `messages/en.json`. Follow the Figma collapsed-state layout (icons-only, tooltip labels).
- [ ] **Step 3: Verify** — both lanes render their nav; collapse persists across reload; keyboard focus order sane; `npm run lint` clean.
- [ ] **Step 4: Commit** — `git commit -am "feat(shell): config-driven sidebar with collapsed mode for both role lanes"`

---### Task 8: Profile + notification preferences (T012/T013, S021/S022)

**Files:**
- Backend — Create: migration (autogenerate), Modify: `backend/app/models/user.py` (add `notification_prefs` JSONB, default `{}`), `backend/app/api/auth.py` (PATCH endpoint), `backend/app/schemas/` (prefs schema)
- Frontend — Create: `frontend/src/app/(app)/teacher/profile/page.tsx`, `.../teacher/notifications/page.tsx`, `.../student/profile/page.tsx`, `.../student/notifications/page.tsx`, `frontend/src/components/settings/notification-preferences-form.tsx`
- Test: `backend/tests/test_notification_prefs.py`

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_notification_prefs.py
import pytest


@pytest.mark.asyncio
async def test_patch_notification_prefs_roundtrip(async_client, logged_in_user):
    payload = {"checkpoint_published": True, "report_ready": True, "follow_up_assigned": False}
    resp = await async_client.patch("/api/auth/me/preferences", json={"notification_prefs": payload})
    assert resp.status_code == 200
    me = await async_client.get("/api/auth/me")
    assert me.json()["data"]["notification_prefs"] == payload


@pytest.mark.asyncio
async def test_patch_rejects_unknown_keys(async_client, logged_in_user):
    resp = await async_client.patch(
        "/api/auth/me/preferences", json={"notification_prefs": {"evil_key": True}}
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: FAIL run** — `pytest tests/test_notification_prefs.py -v` → 404/keyerror.
- [ ] **Step 3: Implement** — model column (`notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")`); Pydantic schema with an explicit whitelist model (`checkpoint_published`, `report_ready`, `follow_up_assigned`, `quiz_due_soon`, `weekly_summary` — all `bool`, `extra="forbid"`); PATCH handler merges into the user row; include `notification_prefs` in the `/auth/me` response schema. Alembic: `alembic revision --autogenerate -m "users.notification_prefs"` → inspect → `alembic upgrade head`.
- [ ] **Step 4: PASS run** — `pytest tests/test_notification_prefs.py tests/test_auth_service.py -v`.
- [ ] **Step 5: Frontend pages** — profile pages reuse the existing settings page content (name, email, language toggle, sign-out) under `PageHeader`; notifications pages render `NotificationPreferencesForm` (switch list driven by the whitelist keys, `patterns.*`/`settings.*` i18n keys, optimistic TanStack mutation). Pull Figma T012/T013/S021/S022 for layout first.
- [ ] **Step 6: Commit** — `git commit -am "feat(profile): notification preferences (whitelisted JSONB) + role-lane profile pages"`

---

### Task 9: Sign-in rebuild, OIDC-ready (T001, S001)

**Files:**
- Modify: `frontend/src/lib/auth.ts` (genericOAuth slots), `frontend/src/app/sign-in/**` (rebuild per Figma), `frontend/src/proxy.ts` (no change expected — confirm `/sign-in` stays public), `frontend/.env.example`
- Create: `docs/oidc-redirect-uris.md`
- Read first: Figma T001 (`1372:8`) + S001 (`1372:200`); `frontend/src/components/auth/*`; Better Auth genericOAuth docs via Context7 (`mcp__plugin_context7_context7__query-docs`, library `better-auth`) — confirm the callback path pattern for the INSTALLED version (`frontend/package.json`).

- [ ] **Step 1: genericOAuth slots** — in `frontend/src/lib/auth.ts`:

```typescript
import { genericOAuth } from "better-auth/plugins";

const hkustOidcProviders = [
  {
    providerId: "hkust-staff",
    clientId: process.env.HKUST_STAFF_MELI_CLIENT_ID ?? "",
    clientSecret: process.env.HKUST_STAFF_MELI_CLIENT_SECRET ?? "",
    discoveryUrl: process.env.HKUST_STAFF_DISCOVERY_URL ?? "",
    scopes: ["openid", "profile", "email"],
  },
  {
    providerId: "hkust-student",
    clientId: process.env.HKUST_STUDENT_MELI_CLIENT_ID ?? "",
    clientSecret: process.env.HKUST_STUDENT_MELI_CLIENT_SECRET ?? "",
    discoveryUrl: process.env.HKUST_STUDENT_DISCOVERY_URL ?? "",
    scopes: ["openid", "profile", "email"],
  },
].filter((p) => p.clientId && p.clientSecret && p.discoveryUrl);

// in betterAuth({ plugins: [...] }):
//   ...(hkustOidcProviders.length ? [genericOAuth({ config: hkustOidcProviders })] : []),
```

Both slots are dormant until env vars exist — zero behavior change today. Add the four env names + discovery URLs to `frontend/.env.example` (values empty; staff discovery URL from the handoff doc may be included as a comment — it is not a secret).

- [ ] **Step 2: Verify callback path** — with the plugin registered (temporarily set dummy env in dev), hit `GET /api/auth/ok` to confirm boot, then confirm the generic OAuth callback route from the installed package source (`node_modules/better-auth/dist/**` — grep `oauth2/callback`) . Expected: `/api/auth/oauth2/callback/:providerId`. Record findings.

- [ ] **Step 3: Write `docs/oidc-redirect-uris.md`** — verified URIs for both providers × {localhost:3000, cle-meli-dev.hkust.edu.hk, cle-meli.hkust.edu.hk}, e.g. `https://cle-meli.hkust.edu.hk/api/auth/oauth2/callback/hkust-staff`; note the staff Entra app's currently-registered URI (`.../callback/hkust`) needs ITSO to update to `/hkust-staff` OR we set `providerId: "hkust"` for staff — flag the decision, default to asking ITSO. Include tenant/app IDs from `docs/meli_docs/Meli_Session_Handoff.md` §3.1. `git add -f` this file.

- [ ] **Step 4: Sign-in UI rebuild** — per Figma T001/S001: single sign-in page, brand panel, email/password form (existing components), Microsoft button (existing), and an "HKUST sign-in" section with Staff / Student buttons rendered ONLY when `process.env.NEXT_PUBLIC_HKUST_SSO === "enabled"` (calls `authClient.signIn.oauth2({ providerId: "hkust-staff" | "hkust-student" })`). Keep `redirect` query-param handling. Invoke `frontend-design` skill; tokens only; both locales' keys under `auth.*`.

- [ ] **Step 5: Verify** — `npm run build` clean; email/password + Microsoft sign-in still work in dev; HKUST buttons absent without the flag.
- [ ] **Step 6: Commit** — `git commit -am "feat(auth): OIDC-ready sign-in (dormant hkust-staff/hkust-student slots, verified callback docs)"`

---

### Task 10: Role-routing E2E + phase close-out

**Files:**
- Create: `frontend/e2e/role-routing.spec.ts`
- Modify: `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md` (tracker + handoff), `docs/superpowers/RESUME.md`

- [ ] **Step 1: E2E spec** (follow auth/fixture patterns from `frontend/e2e/auth.spec.ts` — reuse its login helpers and seeded users)

```typescript
// frontend/e2e/role-routing.spec.ts
import { expect, test } from "@playwright/test";
// Reuse the sign-in helper + seeded instructor/student creds from e2e/auth.spec.ts.

test.describe("role-scoped shells", () => {
  test("instructor lands on /teacher/dashboard and is bounced from /student", async ({ page }) => {
    // signInAs(page, instructor)
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/teacher\/dashboard/);
    await page.goto("/student/dashboard");
    await expect(page).toHaveURL(/\/teacher\/dashboard/);
  });

  test("student lands on /student/dashboard and is bounced from /teacher", async ({ page }) => {
    // signInAs(page, student)
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/student\/dashboard/);
    await page.goto("/teacher/insights");
    await expect(page).toHaveURL(/\/student\/dashboard/);
  });
});
```

- [ ] **Step 2: Run** — `npm run e2e -- role-routing.spec.ts` → green (plus `auth.spec.ts` still green).
- [ ] **Step 3: Full regression** — `cd backend && pytest` (all green), `cd frontend && npm run build && npm run lint`.
- [ ] **Step 4: Close out** — check P0 in the roadmap Phase Tracker; append Handoff Log entry (commits, gotchas, "next: write P1 plan"); update `docs/superpowers/RESUME.md` if anything material changed. `git add -f docs/superpowers/... && git commit -m "docs(roadmap): P0 complete — handoff for P1"`.

---

## Self-review notes (already applied)

- Spec coverage: P0 items from spec §10 all present (config module ✓, route trees ✓, redirects ✓, proxy/role guards → RoleGate + layouts (proxy keeps session gate; role enforcement is layout-level by design since role lives in `public.users`, not the session cookie) ✓, pattern lib P0 subset ✓, sign-in + ITSO doc ✓). Calendar/insights deferrals recorded in roadmap.
- Type consistency: `useRole` return shape preserved across Tasks 3/6/10; `PilotProfile` field names identical backend (snake_case JSON) ↔ frontend types.
- Known adaptation points are explicitly marked (apiFetch/useApiToken signatures, styling idiom, envelope import path, e2e helpers) — executors must read the named file first, not guess.
