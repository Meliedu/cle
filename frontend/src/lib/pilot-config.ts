// Mirrors the backend `PilotProfile` (backend/app/pilot/base.py), served by
// `GET /api/config` inside the standard `ApiEnvelope`. Keep field-for-field in
// sync with the Pydantic model.

export interface ConfidenceScale {
  min: number;
  max: number;
  /** JSON object keys are strings even though the backend uses int keys ("-2".."2"). */
  labels: Record<string, string>;
}

export interface ReadinessQuestion {
  id: string;
  kind: "single_choice" | "multi_choice" | "scale" | "short_text";
  prompt: string;
  options: string[];
}

export interface ReadinessPhaseDef {
  phase: "eligibility_survey" | "ready_check" | "diagnostic";
  title: string;
  intro: string;
  questions: ReadinessQuestion[];
}

export interface PilotConfig {
  id: string;
  institution: string;
  course_family: string;
  terminology: Record<string, string>;
  skill_taxonomy: string[];
  confidence_scale: ConfidenceScale;
  score_category_defaults: { name: string; weight: number | null }[];
  readiness: ReadinessPhaseDef[];
  report_cadence: { weekly: boolean; end_term: boolean };
  role_rules: Record<string, string>;
  locales: string[];
  claim_limits: Record<string, string>;
}
