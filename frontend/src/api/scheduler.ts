/**
 * Typed calls for the scheduler REST surface (api/routers/{owner,pets,tasks,schedule}.py).
 * Feature components call these directly inside React Query hooks — see each
 * component for its query key. Shared query-key convention (keep in sync
 * across features so cache invalidation actually hits the right queries):
 *
 *   ["owner"]                                 — GET /api/owner
 *   ["pets"]                                  — GET /api/pets
 *   ["tasks", { petId, status, sort }]        — GET /api/tasks
 *   ["tasks", "overlaps"]                     — GET /api/tasks/overlaps
 *   ["schedule", date]                        — POST /api/schedule/generate (React Query
 *                                                treats this as a cached read since it's
 *                                                idempotent for a given date)
 *
 * Any mutation that creates/edits/deletes/completes a task must invalidate
 * ["tasks"] (prefix match invalidates every status/sort variant), ["tasks",
 * "overlaps"], and ["schedule"]. Any pet mutation must invalidate ["pets"]
 * and, since tasks embed pet_id, usually ["tasks"] too (a deleted pet's tasks
 * may be affected).
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type {
  OverlapsResponse,
  OwnerRead,
  OwnerUpdate,
  PetCreate,
  PetRead,
  PetUpdate,
  ScheduleGenerateResponse,
  TaskCompleteResponse,
  TaskCreate,
  TaskRead,
  TaskUpdate,
} from "./types";

// -- Owner --------------------------------------------------------------------

export function getOwner(): Promise<OwnerRead> {
  return apiGet<OwnerRead>("/api/owner");
}

export function updateOwner(patch: OwnerUpdate): Promise<OwnerRead> {
  return apiPatch<OwnerRead>("/api/owner", patch);
}

// -- Pets -----------------------------------------------------------------------

export function listPets(): Promise<PetRead[]> {
  return apiGet<PetRead[]>("/api/pets");
}

export function createPet(data: PetCreate): Promise<PetRead> {
  return apiPost<PetRead>("/api/pets", data);
}

export function getPet(petId: string): Promise<PetRead> {
  return apiGet<PetRead>(`/api/pets/${encodeURIComponent(petId)}`);
}

export function updatePet(petId: string, patch: PetUpdate): Promise<PetRead> {
  return apiPatch<PetRead>(`/api/pets/${encodeURIComponent(petId)}`, patch);
}

/** Throws ApiError with status 409 if the pet has health records and
 * `force` was not passed — callers should catch that to offer a confirm-and-
 * force-delete flow rather than surfacing a generic error. */
export function deletePet(petId: string, force = false): Promise<void> {
  const qs = force ? "?force=true" : "";
  return apiDelete<void>(`/api/pets/${encodeURIComponent(petId)}${qs}`);
}

// -- Tasks ----------------------------------------------------------------------

export interface ListTasksParams {
  petId?: string;
  status?: "open" | "completed" | "all";
  sort?: "priority" | "time" | "duration";
}

export function listTasks(params: ListTasksParams = {}): Promise<TaskRead[]> {
  const qs = new URLSearchParams();
  if (params.petId) qs.set("pet_id", params.petId);
  if (params.status) qs.set("status", params.status);
  if (params.sort) qs.set("sort", params.sort);
  const query = qs.toString();
  return apiGet<TaskRead[]>(`/api/tasks${query ? `?${query}` : ""}`);
}

export function getOverlaps(): Promise<OverlapsResponse> {
  return apiGet<OverlapsResponse>("/api/tasks/overlaps");
}

export function createTask(data: TaskCreate): Promise<TaskRead> {
  return apiPost<TaskRead>("/api/tasks", data);
}

export function getTask(taskId: string): Promise<TaskRead> {
  return apiGet<TaskRead>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function updateTask(taskId: string, patch: TaskUpdate): Promise<TaskRead> {
  return apiPatch<TaskRead>(`/api/tasks/${encodeURIComponent(taskId)}`, patch);
}

export function deleteTask(taskId: string): Promise<void> {
  return apiDelete<void>(`/api/tasks/${encodeURIComponent(taskId)}`);
}

export function completeTask(taskId: string): Promise<TaskCompleteResponse> {
  return apiPost<TaskCompleteResponse>(`/api/tasks/${encodeURIComponent(taskId)}/complete`);
}

export function uncompleteTask(taskId: string): Promise<TaskRead> {
  return apiPost<TaskRead>(`/api/tasks/${encodeURIComponent(taskId)}/uncomplete`);
}

// -- Schedule ---------------------------------------------------------------------

/** `date` is an ISO date/datetime string; omit for "today" (server default). */
export function generateSchedule(date?: string): Promise<ScheduleGenerateResponse> {
  const qs = date ? `?date=${encodeURIComponent(date)}` : "";
  return apiPost<ScheduleGenerateResponse>(`/api/schedule/generate${qs}`);
}
