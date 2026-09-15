/**
 * TypeScript mirror of api/schemas/scheduler.py — kept 1:1 with the Pydantic
 * models so payload drift shows up as a compile error. If a backend schema
 * changes, update this file to match (see MIGRATION_PLAN.md §1).
 */

export type Gender = "male" | "female" | "unknown";
export type Priority = "high" | "medium" | "low";
export type Frequency = "once" | "daily" | "weekly" | "monthly" | "as_needed";
export type Category =
  | "feeding"
  | "exercise"
  | "grooming"
  | "medication"
  | "enrichment"
  | "play"
  | "training";

export const GENDER_OPTIONS: Gender[] = ["male", "female", "unknown"];
export const PRIORITY_OPTIONS: Priority[] = ["high", "medium", "low"];
export const FREQUENCY_OPTIONS: Frequency[] = ["once", "daily", "weekly", "monthly", "as_needed"];
export const CATEGORY_OPTIONS: Category[] = [
  "feeding",
  "exercise",
  "grooming",
  "medication",
  "enrichment",
  "play",
  "training",
];

// -- Owner --------------------------------------------------------------------

export interface OwnerRead {
  owner_id: string;
  name: string;
  email: string;
  phone_number: string;
  available_hours_per_day: number;
  work_start_hour: number;
  work_start_minute: number;
  work_end_hour: number;
  work_end_minute: number;
  break_between_tasks_minutes: number;
}

/** PATCH semantics: every field optional, only supplied fields change. */
export interface OwnerUpdate {
  name?: string;
  email?: string;
  phone_number?: string;
  available_hours_per_day?: number;
  work_start_hour?: number;
  work_start_minute?: number;
  work_end_hour?: number;
  work_end_minute?: number;
  break_between_tasks_minutes?: number;
}

// -- Pets -----------------------------------------------------------------------

export interface PetRead {
  pet_id: string;
  owner_id: string;
  name: string;
  pet_type: string;
  age: number;
  age_months: number;
  gender: Gender;
  color: string;
}

export interface PetCreate {
  name: string;
  pet_type: string;
  age: number;
  age_months?: number;
  gender?: Gender;
  color?: string;
}

export interface PetUpdate {
  name?: string;
  pet_type?: string;
  age?: number;
  age_months?: number;
  gender?: Gender;
  color?: string;
}

// -- Tasks ----------------------------------------------------------------------

export interface TaskRead {
  task_id: string;
  owner_id: string;
  pet_id: string | null;
  name: string;
  category: Category;
  duration: number;
  priority: Priority;
  frequency: Frequency;
  notes: string;
  scheduled_time: string;
  due_date: string; // ISO 8601 datetime
  end_date: string | null;
  completed: boolean;
}

export interface TaskCreate {
  name: string;
  category: Category;
  pet_id?: string | null;
  duration: number;
  priority?: Priority;
  frequency?: Frequency;
  notes?: string;
  scheduled_time?: string;
  due_date?: string | null;
  end_date?: string | null;
}

export interface TaskUpdate {
  name?: string;
  category?: Category;
  pet_id?: string | null;
  duration?: number;
  priority?: Priority;
  frequency?: Frequency;
  notes?: string;
  scheduled_time?: string;
  due_date?: string;
  end_date?: string | null;
}

export interface TaskCompleteResponse {
  task: TaskRead;
  next_occurrence: TaskRead | null;
}

// -- Schedule / overlaps ---------------------------------------------------------

export interface ScheduledItem {
  task: TaskRead;
  start: string;
  end: string;
}

export interface ScheduleGenerateResponse {
  schedule: ScheduledItem[];
  conflicts: string[];
}

export interface OverlapsResponse {
  overlaps: string[];
}

// -- Health records ---------------------------------------------------------
// Mirrors pawpal_ai/health_models.py + api/schemas/health.py (see
// MIGRATION_PLAN.md §3/§5). Most response shapes are the pawpal_ai models
// used directly by the API, so the TS side mirrors those, not a re-wrapped
// version.

export type ReviewStatus = "pending" | "approved" | "rejected";
export type CareStatus = "current" | "due_soon" | "overdue" | "unknown";
export type RecordType = "vaccination" | "medication" | "appointment";

export const REVIEW_STATUS_OPTIONS: ReviewStatus[] = ["pending", "approved", "rejected"];

export interface SourceEvidence {
  document_id: string;
  chunk_id: string;
  section: string | null;
  supporting_text: string;
  match_score: number;
}

export interface HealthRecord {
  record_id: string;
  pet_id: string;
  record_type: RecordType;
  fields: Record<string, string | null>;
  evidence: Record<string, SourceEvidence>;
  confidence: number;
  review_status: ReviewStatus;
  care_status: CareStatus;
}

export interface ExtractionResult {
  records: HealthRecord[];
  unsupported_fields: string[];
  missing_fields: string[];
  errors: string[];
  fatal_error: string | null;
  pet_name_in_document: string | null;
  attempts: number;
  injection_flagged: boolean;
  notes: string[];
}

export interface DocumentExtractResponse {
  document_id: string;
  filename: string;
  doc_type: string;
  char_count: number;
  injection_flagged: boolean;
  result: ExtractionResult;
}

/** PATCH semantics: field name -> new value (or null to clear it). Only the
 * given keys change. */
export interface RecordUpdate {
  fields: Record<string, string | null>;
}

export interface Conflict {
  pet_id: string;
  record_type: RecordType;
  field: string;
  value_a: string;
  source_a: SourceEvidence | null;
  value_b: string;
  source_b: SourceEvidence | null;
  resolved: boolean;
}

export interface ConflictRead extends Conflict {
  conflict_id: string;
}

export interface Reminder {
  reminder_id: string;
  pet_id: string;
  record_id: string;
  record_type: RecordType;
  label: string;
  due_date: string; // ISO date
  offsets_days: number[];
  care_status: CareStatus;
  source: SourceEvidence | null;
}

export interface ScheduleCareResponse {
  reminders: Reminder[];
  conflicts: ConflictRead[];
  blocked_record_ids: string[];
}

export interface AskRequest {
  question: string;
  document_id?: string | null;
}

export interface QAAnswer {
  question: string;
  answer: string;
  abstained: boolean;
  refused: boolean;
  citations: SourceEvidence[];
}

export interface AuditEntryRead {
  id: string;
  event: string;
  ref_id: string;
  detail: string;
  created_at: string;
}
