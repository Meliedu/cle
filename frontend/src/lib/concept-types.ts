export type ConceptStatus = "pending" | "approved" | "rejected" | "merged";

export type ConceptTargetKind =
  | "chunk"
  | "question"
  | "flashcard_card"
  | "pronunciation_item"
  | "pool_item"
  | "objective"
  | "meeting"
  | "assignment";

export type MeetingRole = "introduced" | "covered" | "reinforced";

export interface Concept {
  readonly id: string;
  readonly course_id: string;
  readonly name: string;
  readonly description: string | null;
  readonly canonical_id: string | null;
  readonly instructor_curated: boolean;
  readonly status: ConceptStatus;
  readonly extracted_from_chunk_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ConceptPrerequisite {
  readonly prereq_concept_id: string;
  readonly dependent_concept_id: string;
  readonly strength: string;
  readonly instructor_verified: boolean;
  readonly created_at: string;
}

export interface ConceptClusterMember {
  readonly candidate_id: string;
  readonly name: string;
  readonly description: string | null;
  readonly evidence_chunk_id: string | null;
}

export interface ConceptCluster {
  readonly cluster_id: string;
  readonly course_id: string;
  readonly suggested_name: string;
  readonly suggested_description: string | null;
  readonly members: ReadonlyArray<ConceptClusterMember>;
  readonly example_chunk_ids: ReadonlyArray<string>;
  readonly status: "pending" | "approved" | "merged" | "rejected";
}

export type ClusterAction = "approve" | "rename" | "merge" | "reject";

export interface ConceptClusterDecision {
  readonly action: ClusterAction;
  readonly final_name?: string;
  readonly final_description?: string;
  readonly merge_into_concept_id?: string;
}

export interface MasteryRow {
  readonly concept_id: string;
  readonly concept_name: string;
  readonly course_id: string;
  readonly alpha: string;
  readonly beta: string;
  readonly mastery_score: string;
  readonly confidence: string;
  readonly attempt_count: number;
  readonly last_attempt_at: string | null;
  readonly last_decay_at: string;
  readonly updated_at: string;
}

export interface CohortMasteryRow {
  readonly concept_id: string;
  readonly concept_name: string;
  readonly avg_mastery: number | null;
  readonly weak_students: number;
  readonly total_students_with_evidence: number;
}
