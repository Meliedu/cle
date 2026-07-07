# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-07 (P3 in progress — 8/21)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0, P1, P2 COMPLETE; P3 IN PROGRESS (8 of 21 tasks done, next = T9)** — all on `feat/cle-p0-shell`. The P3 detailed plan already exists: `docs/superpowers/plans/2026-07-07-meli-cle-p3-checkpoint-loop.md`. See the roadmap Handoff Log "P3 IN PROGRESS" entry for the T1–T8 commit SHAs, the migration head chain (current head `c3a9f0e1d2b4`), the new services/models, and the T9→T21 remaining list. **Next action: resume P3 at T9 (QR launch signed token).** Cadence note (in that entry): per-task = build + run tests + commit; focused review only for security-sensitive tasks (auth/RLS/token/evidence seam); comprehensive `/code-review` + `/security-review` banked for end-of-build. Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
