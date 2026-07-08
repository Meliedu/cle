# Resume Pointer — read this first in any fresh session

**Last updated:** 2026-07-08 (P0–P7 ALL COMPLETE — roadmap done; next = final /code-review + /security-review gate)

## Active effort: Meli × CLE Checkpoint Loop (Figma "final" flow, 160 screens, 8 phases)

1. Read the roadmap (cross-session contract, phase tracker, handoff log):
   `docs/superpowers/plans/2026-07-07-meli-cle-roadmap.md`
2. Read the approved spec:
   `docs/superpowers/specs/2026-07-06-meli-cle-checkpoint-loop-design.md`
3. Follow the roadmap's **Session bootstrap protocol** — it tells you which phase is next, whether its detailed plan exists, and how to execute + hand off.

Current state: **P0–P7 ALL COMPLETE — the entire 8-phase Meli × CLE roadmap is built** on `feat/cle-p0-shell`. P7 head is `6bc3904` (before the close-out docs commit). Migration head `d5e8b3a6f214`. See the roadmap Handoff Log "P7 COMPLETE" entry for all B1–B11/F1–F6/H1–H4 commit SHAs. Frontend verified: tsc clean, vitest 81 files/360 tests, `npm run build` ✓. Backend: audit-coverage + all P3–P7 suites green in isolation (only the 4 KNOWN pre-existing files fail; the Windows full-suite run has an asyncpg/selector-loop cascade under load — use per-file/sharded runs). **Next action: run the goal's FINAL GATE — `/code-review` then `/security-review` across the full `feat/cle-p0-shell` branch — and fix findings in a loop until clean.** Prioritize the OPEN items in the roadmap "Security findings" section: (1) teacher-cross-user-read-under-`meli_app` verification (affects ALL student-owned tables incl. `reports`); (2) backend dependency bumps (`pyjwt`/`starlette`/`python-multipart` — H1 `pip-audit` flagged 36 advisories, fixes available); (3) `.dockerignore` for seed scripts; (4) the P7 review LOWs (L1–L4); (5) 23 hardcoded strings in pre-existing P1/P2 dialogs. After the gate is clean, the branch is ready to PR to `main`. The two mechanism findings (pooled-GUC reset, scan-time checkpoint re-check) are already FIXED (B10/B11). Known pre-existing backend failures — do NOT chase: test_alerts_evaluator, test_scheduler_integration, test_canvas_coverage, test_live_quiz_service.

Note: `docs/` is gitignored — commit doc files with `git add -f`.

## Completed prior effort: Adaptive Engine (Phases 1–3) + Evidence Engine

Shipped and merged (see git log through PR #2, `8a2c0bc`). The old adaptive-engine resume content is superseded; its specs/plans remain in `docs/superpowers/{specs,plans}/2026-04-*` for reference. Key surviving context (curriculum tables, concept/mastery layer, evidence loop, worker conventions) is summarized in the roadmap's Global Rules and in `CLAUDE.md`.
