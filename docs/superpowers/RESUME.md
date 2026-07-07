# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-07

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P1 (Course setup wizard & gates) is COMPLETE** — all 17 tasks shipped on `feat/cle-p0-shell` (see the roadmap Handoff Log entry dated 2026-07-07 "P1 COMPLETE" for SHAs, the migration head chain, new routers/task types, verification numbers, and the known pre-existing backend-failure list). P0 is also complete. **Next action: write the P2 plan (student entry & enrollment) via `superpowers:writing-plans`** from the P2 phase brief + spec, then execute. P2 reuses P1's `assert_course_open` gate (`context_status='approved'`) + `join_mode`/`enroll_code_active`.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
