# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-08 (P3 COMPLETE — next = P4)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0, P1, P2, P3 COMPLETE; P4 NEXT (plan written, not executed)** — all on `feat/cle-p0-shell`. P3 head is merge commit `c798924`. The P4 detailed plan already exists: `docs/superpowers/plans/2026-07-07-meli-cle-p4-workspace-checklist-calendar.md` (19 tasks: 10 backend / 9 frontend, commit `e25229f`). See the roadmap Handoff Log "P3 COMPLETE" entry for all T9–T21 commit SHAs, the QR security-review outcome, the parallel-worktree cadence, and the P4 review-flags (B5 transactional progress write, B2/B10 work_item_progress RLS, B8 materials preview gating). **Next action: execute P4** task-by-task (backend serial — shared `langassistant_test` DB; frontend independent tracks can parallelize via `git worktree` isolation). Cadence: per-task = build + run tests + commit; focused review only for security-sensitive tasks (auth/RLS/token/evidence seam/grades); comprehensive `/code-review` + `/security-review` banked for end-of-build (after P7). Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
