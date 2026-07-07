# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-08 (P5 COMPLETE — next = P6)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0–P5 COMPLETE; P6 NEXT (plan written, not executed)** — all on `feat/cle-p0-shell`. P5 head is `121b4ec` (fix). Migration head `c7d2f4b9e6a1`. **ALL remaining phase plans are written:** P6 = `2026-07-07-meli-cle-p6-followup-insights.md` (14 tasks: 8 backend / 6 frontend, ZERO new tables — reshapes the existing evidence engine into insights UI); P7 = `2026-07-07-meli-cle-p7-reports-memory-hardening.md` (21 tasks incl. the hardening gate). See the roadmap Handoff Log "P5 COMPLETE" entry for all B1–B12/F1–F10 commit SHAs, the 2 gap-fixes, the 4-parallel-track frontend cadence, and the P6 review-flags (B1 follow_up→work_item seam, B2 worker progress sync, B7 insights access control). **Next action: execute P6** task-by-task (backend serial; frontend parallelizes via `git worktree` isolation — worktrees branch from `main`, so each agent fast-forwards onto the real base itself). Cadence: per-task = build + run tests + commit; focused combined-review only for security-sensitive tasks (auth/RLS/token/evidence seam/grades); comprehensive `/code-review` + `/security-review` banked for after P7 (address ALL findings in the roadmap "Security findings" section — esp. the teacher-cross-user-read-under-`meli_app` verification). Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
