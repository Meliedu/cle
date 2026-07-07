"use client";

import { useAuthedQuery } from "@/hooks/use-authed-query";

/**
 * TanStack hooks over the P6 insights router (`app/api/insights.py`, backend
 * B4–B8). The router is PURE-READ — every field RESHAPES an existing row
 * (`concept_mastery` / `learning_notes` / `outcome_checks` / `instructor_alerts`
 * / `concept_tags` / `learning_objectives`); no number is recomputed. These are
 * all `useAuthedQuery` reads (no mutations live here — the only follow-up write
 * is in `use-follow-ups.ts`). Mirrors the `use-analytics.ts` / `use-work-items.ts`
 * shape: a query-key factory + `useAuthedQuery`.
 *
 * Student reads are enrollment-scoped (`/users/me/courses/{id}/…`); teacher
 * reads are owner-scoped (`/courses/{id}/…`); `useSignal` / `useEvidenceSource`
 * resolve a single id, re-derive the course, and re-apply the guard.
 */

// ----- shared value types -----

/** One concept row in the learning profile, RESHAPED from `concept_mastery`. */
export interface ConceptMasteryEntry {
  readonly concept_id: string;
  readonly concept_name: string;
  readonly mastery_score: number;
  readonly confidence: number;
  readonly attempt_count: number;
  readonly last_attempt_at: string | null;
}

/** Strong / developing / weak grouping (same thresholds as `cohort_mastery`). */
export interface ConceptGroups {
  readonly strong: readonly ConceptMasteryEntry[];
  readonly developing: readonly ConceptMasteryEntry[];
  readonly weak: readonly ConceptMasteryEntry[];
}

/** Mirrors the student learning-profile payload (`GET /users/me/courses/{id}/insights`). */
export interface LearningProfile {
  readonly course_id: string;
  readonly has_evidence: boolean;
  readonly concept_count: number;
  readonly groups: ConceptGroups;
  /** The pilot `claim_limits['learning_profile']` disclaimer, verbatim. */
  readonly disclaimer: string;
}

/** One objective row in the STUDENT ILO strength map. */
export interface StudentIloObjective {
  readonly objective_id: string;
  readonly statement: string;
  readonly bloom_level: string | null;
  readonly has_evidence: boolean;
  readonly strength: number | null;
  readonly concept_count: number;
  readonly evidence_concept_count: number;
}

/** Mirrors the student ILO map (`GET /users/me/courses/{id}/ilo-map`). */
export interface StudentIloMap {
  readonly course_id: string;
  readonly has_evidence: boolean;
  readonly objectives: readonly StudentIloObjective[];
}

/** One objective row in the COHORT (teacher) ILO strength map. */
export interface CohortIloObjective {
  readonly objective_id: string;
  readonly statement: string;
  readonly bloom_level: string | null;
  readonly has_evidence: boolean;
  readonly avg_strength: number | null;
  readonly weak_students: number;
  readonly students_with_evidence: number;
  readonly concept_count: number;
}

/** Mirrors the teacher ILO map (`GET /courses/{id}/ilo-map`). */
export interface CohortIloMap {
  readonly course_id: string;
  readonly has_evidence: boolean;
  readonly objectives: readonly CohortIloObjective[];
}

/**
 * One skill cell in the honest config-driven skill map. No schema link exists
 * (Decision 5), so `has_evidence` is always `false` and `strength`/`sample_size`
 * are always `null` — the forward-compatible seam for a future concept→skill map.
 */
export interface SkillMapEntry {
  readonly skill: string;
  readonly label: string;
  readonly has_evidence: false;
  readonly strength: null;
  readonly sample_size: null;
}

/** Mirrors the skill pattern map (`GET /users/me/courses/{id}/skill-map`). */
export interface SkillMap {
  readonly course_id: string;
  readonly has_evidence: false;
  readonly skills: readonly SkillMapEntry[];
}

/**
 * Mirrors the signal detail (`GET /signals/{id}`). A `learning_note` reshaped —
 * content fields are `null` while `waiting_for_review` (an unreviewed AI draft is
 * never exposed, Core §0.2 / Decision 6).
 */
export interface SignalDetail {
  readonly id: string;
  readonly course_id: string;
  readonly user_id: string | null;
  readonly review_status: string;
  readonly waiting_for_review: boolean;
  readonly created_at: string;
  readonly updated_at: string;
  readonly evidence_category?: string | null;
  readonly observed_signal?: string | null;
  readonly draft_interpretation?: string | null;
  readonly limitation_note?: string | null;
  readonly context_anchor?: string | null;
  readonly outcome_status?: string | null;
  readonly source_event_ids: readonly string[];
}

/**
 * Mirrors the evidence source view (`GET /evidence/{id}/source`) — the raw
 * `learning_event` a signal traces back to ("where did this come from").
 */
export interface EvidenceSource {
  readonly event_id: string;
  readonly course_id: string;
  readonly user_id: string | null;
  readonly source_kind: string;
  readonly source_id?: string | null;
  readonly stage: string;
  readonly event_type: string;
  readonly value: Record<string, unknown>;
  readonly occurred_at: string;
  readonly context_anchor?: string | null;
}

/** Cohort mastery summary block on the teacher course-insights payload. */
export interface CohortMasterySummary {
  readonly concept_count: number;
  readonly concepts_with_evidence: number;
  readonly avg_mastery: number | null;
  readonly weak_student_signals: number;
}

/** Open-alert severity counts (mirrors `GET /courses/{id}/alerts?status=open`). */
export interface AlertCounts {
  readonly info: number;
  readonly warning: number;
  readonly critical: number;
  readonly total: number;
}

/** Review-queue depth: open alerts + `draft`/`queued` notes awaiting review. */
export interface ReviewQueueDepth {
  readonly open_alerts: number;
  readonly pending_notes: number;
  readonly total: number;
}

/** Mirrors the teacher course insights (`GET /courses/{id}/insights`). */
export interface CourseInsights {
  readonly course_id: string;
  readonly has_evidence: boolean;
  readonly cohort_mastery: CohortMasterySummary;
  readonly alerts: AlertCounts;
  readonly review_queue: ReviewQueueDepth;
}

/** `outcome_checks.status` counts (the effectiveness breakdown). */
export interface OutcomeStatusCounts {
  readonly pending: number;
  readonly completed: number;
  readonly improved: number;
  readonly persistent: number;
  readonly resolved: number;
  readonly needs_review: number;
  readonly carried_forward: number;
}

/** One follow-up action-type row in the effectiveness tracker. */
export interface EffectivenessByActionType {
  readonly action_type: string;
  readonly total: number;
  readonly by_status: OutcomeStatusCounts;
}

/** Mirrors the effectiveness tracker (`GET /courses/{id}/effectiveness`). */
export interface Effectiveness {
  readonly course_id: string;
  readonly has_evidence: boolean;
  readonly total: number;
  readonly by_status: OutcomeStatusCounts;
  readonly by_action_type: readonly EffectivenessByActionType[];
}

// ----- query-key factory -----

export const insightKeys = {
  learningProfile: (courseId: string) =>
    ["insights", "learning-profile", courseId] as const,
  iloMap: (courseId: string) => ["insights", "ilo-map", courseId] as const,
  cohortIloMap: (courseId: string) =>
    ["insights", "cohort-ilo-map", courseId] as const,
  skillMap: (courseId: string) => ["insights", "skill-map", courseId] as const,
  signal: (signalId: string) => ["insights", "signal", signalId] as const,
  evidenceSource: (eventId: string) =>
    ["insights", "evidence-source", eventId] as const,
  courseInsights: (courseId: string) =>
    ["insights", "course", courseId] as const,
  effectiveness: (courseId: string) =>
    ["insights", "effectiveness", courseId] as const,
};

// ----- student reads (enrollment-scoped) -----

/**
 * GET `/users/me/courses/{id}/insights` — the caller's learning profile,
 * RESHAPED from `concept_mastery` into strong/developing/weak groups plus the
 * pilot disclaimer. A student with no mastery rows returns `has_evidence=false`.
 */
export function useLearningProfile(courseId: string) {
  return useAuthedQuery<LearningProfile>({
    queryKey: insightKeys.learningProfile(courseId),
    path: `/users/me/courses/${courseId}/insights`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/users/me/courses/{id}/ilo-map` — one row per learning objective with the
 * caller's aggregate strength over the concepts tagged to it. Objectives with no
 * evidence-bearing concept render `has_evidence=false` (never a fabricated 0).
 */
export function useIloMap(courseId: string) {
  return useAuthedQuery<StudentIloMap>({
    queryKey: insightKeys.iloMap(courseId),
    path: `/users/me/courses/${courseId}/ilo-map`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/users/me/courses/{id}/skill-map` — the honest config skill grid. Every
 * cell is `has_evidence=false` (Decision 5): no concept→skill link exists, so no
 * score is ever fabricated.
 */
export function useSkillMap(courseId: string) {
  return useAuthedQuery<SkillMap>({
    queryKey: insightKeys.skillMap(courseId),
    path: `/users/me/courses/${courseId}/skill-map`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/signals/{id}` — one signal (`learning_note`) detail. The backend
 * re-derives the course and re-applies the owner/enrollment guard (404 on
 * mismatch); content is withheld while `waiting_for_review`.
 */
export function useSignal(signalId: string | null) {
  return useAuthedQuery<SignalDetail>({
    queryKey: insightKeys.signal(signalId ?? ""),
    path: `/signals/${signalId}`,
    enabled: Boolean(signalId),
  });
}

/**
 * GET `/evidence/{id}/source` — the `learning_event` a signal traces back to.
 * Same re-derived guard (id never trusted, Decision 8).
 */
export function useEvidenceSource(eventId: string | null) {
  return useAuthedQuery<EvidenceSource>({
    queryKey: insightKeys.evidenceSource(eventId ?? ""),
    path: `/evidence/${eventId}/source`,
    enabled: Boolean(eventId),
  });
}

// ----- teacher reads (owner-scoped) -----

/**
 * GET `/courses/{id}/insights` — the owner's course insights: cohort mastery
 * summary + open-alert severity counts + review-queue depth. Recomputes nothing.
 */
export function useCourseInsights(courseId: string) {
  return useAuthedQuery<CourseInsights>({
    queryKey: insightKeys.courseInsights(courseId),
    path: `/courses/${courseId}/insights`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/courses/{id}/effectiveness` — `outcome_checks` grouped by status and by
 * follow-up `action_type` (the read side of the evidence loop, Decision 9).
 */
export function useEffectiveness(courseId: string) {
  return useAuthedQuery<Effectiveness>({
    queryKey: insightKeys.effectiveness(courseId),
    path: `/courses/${courseId}/effectiveness`,
    enabled: Boolean(courseId),
  });
}

/**
 * GET `/courses/{id}/ilo-map` — the teacher cohort ILO strength map (avg strength
 * + weak-student count per objective). Owner-scoped; 404 on a non-owner.
 */
export function useCohortIloMap(courseId: string) {
  return useAuthedQuery<CohortIloMap>({
    queryKey: insightKeys.cohortIloMap(courseId),
    path: `/courses/${courseId}/ilo-map`,
    enabled: Boolean(courseId),
  });
}
