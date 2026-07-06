# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-07

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0 (Shell & foundations) is COMPLETE** — all 10 tasks shipped (see the roadmap Handoff Log entry dated 2026-07-07 for SHAs, verification numbers, and the known pre-existing backend-failure list). **Next action: PR `feat/cle-p0-shell` to main, then write the P1 plan** (course setup wizard & gates) via `superpowers:writing-plans` from the P1 phase brief + spec, and execute it.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
