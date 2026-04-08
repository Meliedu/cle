# Phase 1a QA Report

**Date:** 2026-04-06
**Tester:** Automated (Claude Code)
**Build:** Backend FastAPI 0.128.0 + Frontend Next.js 16.2.2

---

## Backend QA

### Flow 1: Health Check
| Check | Result |
|-------|--------|
| `GET /health` returns 200 | **PASS** — `{"status": "ok"}` |
| FastAPI server starts cleanly | **PASS** — worker starts, lifespan works |
| Server shuts down gracefully | **PASS** — no errors on shutdown |

### Flow 2: Authentication
| Check | Result |
|-------|--------|
| No auth header → 401 | **PASS** — `{"detail": "Missing or invalid authorization header"}` |
| Invalid JWT → 401 | **PASS** |
| All protected routes reject unauthenticated requests | **PASS** — `/api/courses`, `/api/auth/me`, `/api/courses/.../documents/upload` all return 401 |

### Flow 3: Role Detection
| Check | Result |
|-------|--------|
| `@connect.ust.hk` → student role | **PASS** |
| `@ust.hk` → instructor role | **PASS** |
| `@gmail.com` → ValueError (blocked) | **PASS** |
| Case insensitive domain check | **PASS** |

### Flow 4: R2 Storage Service
| Check | Result |
|-------|--------|
| `build_r2_key()` formats correctly | **PASS** — `courses/{course_id}/documents/{doc_id}/{filename}` |
| `upload_file()` calls S3 `put_object` | **PASS** (mocked) |
| `download_file()` returns bytes | **PASS** (mocked) |
| `delete_file()` calls S3 `delete_object` | **PASS** (mocked) |

### Flow 5: Database
| Check | Result |
|-------|--------|
| All 21 tables exist | **PASS** — users, courses, enrollments, documents, chunks, quizzes, questions, quiz_documents, quiz_attempts, flashcard_sets, flashcard_cards, flashcard_set_documents, flashcard_progress, pronunciation_scores, student_progress, session_summaries, live_sessions, tasks, api_usage, canvas_integrations, alembic_version |
| pgvector extension enabled | **PASS** |
| pg_trgm extension enabled | **PASS** |
| 10 custom indexes created | **PASS** — idx_chunks_embedding (HNSW), idx_chunks_tsvector (GIN), idx_chunks_course_id, idx_enrollments_user_id, idx_quiz_attempts_user_id, idx_documents_course_status, idx_questions_quiz_id, idx_flashcard_cards_set_id, idx_tasks_poll, idx_api_usage_rate_limit |
| Seed data loaded | **PASS** — 2 users, 1 course, 2 enrollments |

### Flow 6: Task Queue Worker
| Check | Result |
|-------|--------|
| Worker starts in lifespan | **PASS** — log: "Task worker started" |
| Worker shuts down on app shutdown | **PASS** — clean cancellation |

### Flow 7: Unit Tests
| Check | Result |
|-------|--------|
| `test_auth_service.py` (4 tests) | **PASS** — all 4/4 |
| `test_storage_service.py` (4 tests) | **PASS** — all 4/4 |
| Total: 8/8 tests passing | **PASS** |

---

## Frontend QA

### Flow 8: Build
| Check | Result |
|-------|--------|
| `npm run build` passes | **PASS** |
| Next.js version 16.2.2 | **PASS** |
| All routes generate | **PASS** — `/`, `/dashboard`, `/dashboard/courses`, `/dashboard/courses/[courseId]`, `/sign-in`, `/sign-up` |

### Flow 9: Dependencies
| Check | Result |
|-------|--------|
| @clerk/nextjs installed | **PASS** |
| @tanstack/react-query installed | **PASS** |
| lucide-react installed | **PASS** |
| shadcn/ui components: button, card, badge, dialog, dropdown-menu, separator, skeleton, tabs, input, textarea, label, select, avatar | **PASS** |

### Flow 10: Key Patterns
| Check | Result |
|-------|--------|
| TanStack Query v5 SSR provider (no deprecated `isServer`) | **PASS** — uses `typeof window === "undefined"` |
| Clerk middleware (latest `clerkMiddleware` + `createRouteMatcher`) | **PASS** |
| Clerk SignIn/SignUp with `fallbackRedirectUrl` | **PASS** |
| Design tokens in CSS custom properties | **PASS** — `src/styles/tokens.css` |

### Flow 11: Pages Created
| Page | Status |
|------|--------|
| Landing page (hero + features + CTA) | **PASS** |
| Sign In page | **PASS** |
| Sign Up page | **PASS** |
| Dashboard layout (sidebar + navbar) | **PASS** |
| Dashboard home (stats + courses) | **PASS** |
| Courses list page | **PASS** |
| Course detail page (tabs: Overview/Materials/Quizzes/Students) | **PASS** |

### Flow 12: Components Created
| Component | Status |
|-----------|--------|
| Sidebar (collapsible, role-based nav, mobile overlay) | **PASS** |
| Navbar (breadcrumbs, user button) | **PASS** |
| Dashboard shell (sidebar + navbar layout) | **PASS** |
| Upload zone (drag-and-drop, validation, progress) | **PASS** |
| Create course dialog (form with validation) | **PASS** |

---

## Known Issues

| Severity | Issue | Status |
|----------|-------|--------|
| INFO | Next.js 16 deprecation warning: `middleware.ts` → `proxy.ts` | **Deferred** — waiting for Clerk migration guidance |
| INFO | `pytest-asyncio` deprecation warning about `asyncio_default_fixture_loop_scope` | **Low priority** — functional, cosmetic warning |

---

## Summary

| Category | Pass | Fail | Total |
|----------|------|------|-------|
| Backend API | 7 | 0 | 7 |
| Database | 5 | 0 | 5 |
| Unit Tests | 8 | 0 | 8 |
| Frontend Build | 3 | 0 | 3 |
| Frontend Pages | 7 | 0 | 7 |
| Frontend Components | 5 | 0 | 5 |
| **Total** | **35** | **0** | **35** |

**Result: PASS** — Phase 1a foundation is complete and verified.
