export type MeetingStatus = "planned" | "in_progress" | "taught" | "cancelled";
export type BloomLevel =
  | "remember"
  | "understand"
  | "apply"
  | "analyze"
  | "evaluate"
  | "create";
export type AssignmentKind =
  | "essay"
  | "project"
  | "quiz"
  | "reading"
  | "presentation"
  | "lab"
  | "problem_set"
  | "participation"
  | "other";
export type SubmissionStatus =
  | "not_started"
  | "in_progress"
  | "submitted"
  | "late"
  | "graded"
  | "excused";
export type SyllabusImportStatus =
  | "pending"
  | "parsed"
  | "applied"
  | "failed"
  | "superseded";

export interface CourseModule {
  readonly id: string;
  readonly course_id: string;
  readonly parent_id: string | null;
  readonly name: string;
  readonly description: string | null;
  readonly order_index: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CourseMeeting {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_index: number;
  readonly title: string | null;
  readonly scheduled_at: string;
  readonly duration_minutes: number;
  readonly location: string | null;
  readonly status: MeetingStatus;
  readonly canvas_event_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface LearningObjective {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_id: string | null;
  readonly statement: string;
  readonly bloom_level: BloomLevel | null;
  readonly order_index: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface Assignment {
  readonly id: string;
  readonly course_id: string;
  readonly module_id: string | null;
  readonly meeting_id: string | null;
  readonly title: string;
  readonly description: string | null;
  readonly kind: AssignmentKind;
  readonly due_at: string;
  readonly available_from: string | null;
  readonly weight: string | null;
  readonly quiz_id: string | null;
  readonly is_published: boolean;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AssignmentSubmission {
  readonly id: string;
  readonly assignment_id: string;
  readonly user_id: string;
  readonly status: SubmissionStatus;
  readonly submitted_at: string | null;
  readonly score: string | null;
  readonly feedback: string | null;
  readonly submission_payload: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface SyllabusImport {
  readonly id: string;
  readonly course_id: string;
  readonly document_id: string | null;
  readonly parsed_payload: Record<string, unknown>;
  readonly status: SyllabusImportStatus;
  readonly error_message: string | null;
  readonly applied_at: string | null;
  readonly applied_by: string | null;
  readonly created_by: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface CalendarEvent {
  readonly id: string;
  readonly kind: "meeting" | "assignment";
  readonly title: string;
  readonly at: string;
  readonly duration_minutes?: number;
  readonly location?: string | null;
  readonly status?: MeetingStatus;
  readonly assignment_kind?: AssignmentKind;
  readonly weight?: number | null;
}
