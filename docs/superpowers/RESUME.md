# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-08 (P4 COMPLETE — next = P5)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0–P4 COMPLETE; P5 NEXT (plan written, not executed)** — all on `feat/cle-p0-shell`. P4 head is merge commit `603e990`. Migration head `e6c2b8f4a19d`. The P5 detailed plan already exists: `docs/superpowers/plans/2026-07-07-meli-cle-p5-practice-quiz-activities-score.md` (22 tasks: 12 backend / 10 frontend). The P6 plan is ALSO written (`2026-07-07-meli-cle-p6-followup-insights.md`, 14 tasks, zero new tables). See the roadmap Handoff Log "P4 COMPLETE" entry for all B1–B10/F1–F9 commit SHAs, the fixed HIGH (`d417285` calendar active-enrollment), the 3 tracked LOWs, the 3-parallel-track frontend cadence, and the P5 review-flags (B11 grade export, B3/B12 activity_responses RLS, B6/B9 evidence seam, B4/B5/B8 score gate). **Next action: execute P5** task-by-task (backend serial — shared `langassistant_test` DB; frontend independent tracks parallelize via `git worktree` isolation — NOTE worktrees branch from `main`, so each agent must fast-forward onto the real base itself). Cadence: per-task = build + run tests + commit; focused combined-review only for security-sensitive tasks (auth/RLS/token/evidence seam/grades); comprehensive `/code-review` + `/security-review` banked for end-of-build (after P7). Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
