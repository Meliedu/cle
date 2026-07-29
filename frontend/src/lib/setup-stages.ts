/**
 * The five user-facing setup stages (Plate 05).
 *
 *   Current   Ten implementation-flavoured steps expose the internal workflow.
 *   Target    Five user-facing stages: Basics, Sources, Schedule, Review,
 *             Publish.
 *   Rule      Keep sub-state in the data model; never turn every backend
 *             operation into a top-level step.
 *
 * The backend's nine `SETUP_STEP_KEYS` are unchanged: they remain the unit of
 * completion, validation, and publish gating. This module is purely the
 * projection from those nine keys onto the five stages a user sees, so no state
 * identity is lost (the handoff is explicit that sharing a route or component
 * "is not permission to remove success, loading, empty, error, locked, blocked,
 * or recovery behavior").
 */

import { courseLifecycle } from "@/lib/contracts/state";
import type { SetupState, SetupStepKey } from "@/hooks/use-setup";

export type SetupStage =
  | "basics"
  | "sources"
  | "schedule"
  | "review"
  | "publish";

export const SETUP_STAGES: readonly SetupStage[] = [
  "basics",
  "sources",
  "schedule",
  "review",
  "publish",
] as const;

/**
 * Which backend steps each stage owns.
 *
 * Sources absorbs syllabus, materials, and the analyzer pass because to a user
 * those are one job: give Meli the course material and wait for it to be read.
 * Review absorbs outcomes, checkpoints, scoring, and class code because they
 * are all "confirm what Meli derived before anyone sees it".
 *
 * Publish owns no step flag. Publishing is the action, not a checklist item.
 */
export const STAGE_STEPS: Record<SetupStage, readonly SetupStepKey[]> = {
  basics: ["basics"],
  sources: ["syllabus", "materials", "analyzer_review"],
  schedule: ["schedule"],
  review: ["ilo_map", "checkpoints", "score_policy", "class_code"],
  publish: [],
};

export type StageStatus = "complete" | "current" | "pending";

/** Which stage owns a given backend step key. */
export function stageForStep(step: SetupStepKey): SetupStage {
  for (const stage of SETUP_STAGES) {
    if (STAGE_STEPS[stage].includes(step)) return stage;
  }
  return "publish";
}

export interface StageProgress {
  readonly done: number;
  readonly total: number;
  readonly complete: boolean;
}

/** How much of a stage's underlying work is finished. */
export function stageProgress(
  stage: SetupStage,
  steps: Readonly<Record<string, boolean>>
): StageProgress {
  const owned = STAGE_STEPS[stage];
  const done = owned.filter((step) => Boolean(steps[step])).length;
  return { done, total: owned.length, complete: owned.length > 0 && done === owned.length };
}

function isPublished(state: SetupState | undefined): boolean {
  // Delegate rather than restate the rule. courseLifecycle is the one place
  // lifecycle is derived; a second copy here is how the two drift apart.
  return state ? courseLifecycle(state) === "published" : false;
}

/**
 * The stage the user should land on.
 *
 * A published course lands on Publish (its terminal, success state). Otherwise
 * it is the first stage with outstanding work, falling back to Publish once
 * everything is done and only the action remains.
 */
export function firstIncompleteStage(
  state: SetupState | undefined
): SetupStage {
  if (!state) return "basics";
  if (isPublished(state)) return "publish";
  const found = SETUP_STAGES.find(
    (stage) =>
      STAGE_STEPS[stage].length > 0 && !stageProgress(stage, state.steps).complete
  );
  return found ?? "publish";
}

/**
 * Status of every stage, for the stepper.
 *
 * Exactly one stage is `current`. A stage after the current one is `pending`
 * even if its steps happen to be done, so the stepper reads as a path rather
 * than a scatter of ticks.
 */
export function stageStatuses(
  state: SetupState | undefined,
  currentStage: SetupStage
): Record<SetupStage, StageStatus> {
  const currentIndex = SETUP_STAGES.indexOf(currentStage);
  const steps = state?.steps ?? {};
  const published = isPublished(state);

  const result = {} as Record<SetupStage, StageStatus>;
  SETUP_STAGES.forEach((stage, index) => {
    if (stage === currentStage) {
      result[stage] = "current";
      return;
    }
    if (stage === "publish") {
      result[stage] = published ? "complete" : "pending";
      return;
    }
    // A stage only reads "complete" when it is BEHIND the current one. A later
    // stage whose steps happen to be done stays "pending" so the stepper reads
    // as a path rather than a scatter of ticks: navigating back to Basics must
    // not make Review look finished ahead of where the user actually is.
    const complete = stageProgress(stage, steps).complete;
    result[stage] = index < currentIndex && complete ? "complete" : "pending";
  });
  return result;
}

/**
 * Whether a stage can be opened.
 *
 * Every stage before the first incomplete one is reachable, plus the first
 * incomplete stage itself. Stages beyond that stay closed so a user cannot land
 * on Review before there is anything to review. Publish additionally requires
 * every gating step to be done.
 */
export function stageIsReachable(
  stage: SetupStage,
  state: SetupState | undefined
): boolean {
  if (!state) return stage === "basics";
  if (isPublished(state)) return true;

  const frontier = SETUP_STAGES.indexOf(firstIncompleteStage(state));
  const index = SETUP_STAGES.indexOf(stage);
  if (index > frontier) return false;
  if (stage === "publish") return state.missing.length === 0;
  return true;
}

/** Backend step keys still outstanding within a stage. */
export function missingStepsForStage(
  stage: SetupStage,
  state: SetupState | undefined
): readonly SetupStepKey[] {
  const steps = state?.steps ?? {};
  return STAGE_STEPS[stage].filter((step) => !steps[step]);
}
