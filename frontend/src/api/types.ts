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
