# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-08 (P6 COMPLETE — next = P7, the final phase)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0–P6 COMPLETE; P7 NEXT (the FINAL phase — plan written, not executed)** — all on `feat/cle-p0-shell`. P6 head is `3563ecb`. Migration head `c7d2f4b9e6a1` (P6 added no migration). The P7 detailed plan already exists: `2026-07-07-meli-cle-p7-reports-memory-hardening.md` (21 tasks: 11 backend / 6 frontend / 4 hardening). See the roadmap Handoff Log "P6 COMPLETE" entry for all B1–B8/F1–F6 commit SHAs, the inline security fix (`8f26dfa`), the 2-parallel-track cadence, and the P7 review-flags (B3 report unreviewed-content-leak, B6 send-gate+audit, B1 reports read model, B10/B11 security-finding fixes). **Next action: execute P7** task-by-task (backend serial — reports+audit_events tables are NEW, so a migration chain from `c7d2f4b9e6a1`; frontend parallelizes via `git worktree` — worktrees branch from `main`, each agent fast-forwards onto the real base itself; NOTE `teacher/insights/page.tsx` + other overhaul files are uncommitted — any P7 task touching them runs in the MAIN tree with no-destructive-git guardrails). P7 hardening ADDRESSES all tracked "Security findings". **AFTER P7: run `/code-review` then `/security-review` on the full branch and fix in a loop until clean** — the goal's final gate. Cadence: per-task = build + run tests + commit; focused combined-review only for security-sensitive tasks (auth/RLS/reports-content-leak/send-gate/audit). Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
