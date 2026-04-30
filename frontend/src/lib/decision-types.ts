// frontend/src/lib/decision-types.ts
export type ActionType =
  | "review_concept"
  | "prep_meeting"
  | "complete_assignment"
  | "do_quiz"
  | "practice_weakness"
  | "catch_up_reading"
  | "flashcard_review"
  | "pronunciation_practice"
  | "watch_recording";

export type NextActionTargetKind =
  | "concept"
  | "course_meeting"
  | "assignment"
  | "quiz"
  | "flashcard_set"
  | "pronunciation_set"
  | "document"
  | "chunk";

export type CandidateSource =
  | "outer_fringe"
  | "deadline"
  | "review"
  | "fallback";

export type EngineMode = "on" | "off" | "random_50";
export type OverrideMode = "on" | "off";

export type AlertType =
  | "student_disengaging"
  | "student_falling_behind"
  | "cohort_concept_weakness"
  | "prereq_gap_for_upcoming_meeting"
  | "low_quiz_participation"
  | "missed_deadline"
  | "content_gap";

export type AlertSeverity = "info" | "warning" | "critical";
export type AlertStatus = "open" | "dismissed" | "resolved";

export interface NextAction {
  readonly id: string;
  readonly user_id: string;
  readonly course_id: string | null;
  readonly action_type: ActionType;
  readonly target_kind: NextActionTargetKind | null;
  readonly target_id: string | null;
  readonly priority_score: string;
  readonly candidate_source: CandidateSource;
  readonly reason: Record<string, unknown>;
  readonly expires_at: string;
  readonly served_at: string | null;
  readonly clicked_at: string | null;
  readonly consumed_at: string | null;
  readonly engine_variant: string;
  readonly created_at: string;
}

export interface NextActionClick {
  readonly id: string;
  readonly clicked_at: string;
  readonly target_kind: NextActionTargetKind | null;
  readonly target_id: string | null;
}

export interface EngineSettings {
  readonly course_id: string;
  readonly mode: EngineMode;
  readonly overrides_count: number;
}

export interface EngineOverride {
  readonly user_id: string;
  readonly course_id: string;
  readonly mode: OverrideMode;
  readonly set_by: string;
  readonly set_at: string;
}

export interface InstructorAlert {
  readonly id: string;
  readonly course_id: string;
  readonly instructor_id: string;
  readonly target_user_id: string | null;
  readonly alert_type: AlertType;
  readonly severity: AlertSeverity;
  readonly title: string;
  readonly reason: Record<string, unknown>;
  readonly status: AlertStatus;
  readonly resolved_at: string | null;
  readonly resolved_by: string | null;
  readonly created_at: string;
}
