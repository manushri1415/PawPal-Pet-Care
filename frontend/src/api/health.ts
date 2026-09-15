/**
 * Typed calls for the health-records REST surface (api/routers/health.py).
 * Feature components call these directly inside React Query hooks — see
 * each component for its query key. Shared query-key convention (keep in
 * sync across features so cache invalidation actually hits the right
 * queries):
 *
 *   ["health", "records", petId, reviewStatus]     — GET /api/health/pets/{petId}/records
 *   ["health", "record", recordId]                 — GET /api/health/records/{id}
 *   ["health", "reminders", petId]                 — GET /api/health/pets/{petId}/reminders
 *   ["health", "conflicts", petId, unresolvedOnly] — GET /api/health/pets/{petId}/conflicts
 *   ["health", "audit", limit]                     — GET /api/health/audit
 *
 * Approve/reject/update a record -> invalidate ["health", "records"] (prefix
 * match hits every pet/status variant). Schedule-care -> invalidate
 * ["health", "reminders"] and ["health", "conflicts"] (it recomputes both).
 * Resolve a conflict -> invalidate ["health", "conflicts"].
 *
 * `extractDocument` and `ask` are the two AI-gated calls (see
 * MIGRATION_PLAN.md §4); api/client.ts attaches the owner key from
 * `lib/ownerKey.ts` to every request when one is set. A missing/wrong key surfaces as `ApiError` with status
 * 401 (or 503 if the server has no key configured at all) — callers should
 * catch that and render the inline "enter your owner key" prompt rather than
 * a generic error (see OwnerKeyGate.tsx).
 */

import { apiGet, apiPatch, apiPost, apiPostForm } from "./client";
import type {
  AskRequest,
  AuditEntryRead,
  ConflictRead,
  DocumentExtractResponse,
  HealthRecord,
  QAAnswer,
  RecordUpdate,
  Reminder,
  ReviewStatus,
  ScheduleCareResponse,
} from "./types";

function petPath(petId: string): string {
  return `/api/health/pets/${encodeURIComponent(petId)}`;
}

// -- Documents / extraction (🔒 AI-gated) --------------------------------------

/** Extract records from an uploaded file. */
export function extractDocumentFromFile(
  petId: string,
  file: File,
): Promise<DocumentExtractResponse> {
  const form = new FormData();
  form.append("file", file);
  return apiPostForm<DocumentExtractResponse>(
    `${petPath(petId)}/documents:extract`,
    form,
  );
}

/** Extract records from pasted text. */
export function extractDocumentFromText(
  petId: string,
  text: string,
): Promise<DocumentExtractResponse> {
  const form = new FormData();
  form.append("text", text);
  return apiPostForm<DocumentExtractResponse>(
    `${petPath(petId)}/documents:extract`,
    form,
  );
}

// -- Review (free) --------------------------------------------------------------

export function listRecords(
  petId: string,
  reviewStatus?: ReviewStatus,
): Promise<HealthRecord[]> {
  const qs = reviewStatus ? `?review_status=${reviewStatus}` : "";
  return apiGet<HealthRecord[]>(`${petPath(petId)}/records${qs}`);
}

export function getRecord(recordId: string): Promise<HealthRecord> {
  return apiGet<HealthRecord>(`/api/health/records/${encodeURIComponent(recordId)}`);
}

export function approveRecord(recordId: string): Promise<HealthRecord> {
  return apiPost<HealthRecord>(`/api/health/records/${encodeURIComponent(recordId)}/approve`);
}

export function rejectRecord(recordId: string): Promise<HealthRecord> {
  return apiPost<HealthRecord>(`/api/health/records/${encodeURIComponent(recordId)}/reject`);
}

export function updateRecord(recordId: string, patch: RecordUpdate): Promise<HealthRecord> {
  return apiPatch<HealthRecord>(`/api/health/records/${encodeURIComponent(recordId)}`, patch);
}

// -- Reminders & conflicts (free) ------------------------------------------------

export function scheduleCare(petId: string): Promise<ScheduleCareResponse> {
  return apiPost<ScheduleCareResponse>(`${petPath(petId)}/schedule-care`);
}

export function listReminders(petId: string): Promise<Reminder[]> {
  return apiGet<Reminder[]>(`${petPath(petId)}/reminders`);
}

export function listConflicts(
  petId: string,
  unresolvedOnly = false,
): Promise<ConflictRead[]> {
  const qs = unresolvedOnly ? "?unresolved_only=true" : "";
  return apiGet<ConflictRead[]>(`${petPath(petId)}/conflicts${qs}`);
}

export function resolveConflict(conflictId: string): Promise<ConflictRead> {
  return apiPost<ConflictRead>(`/api/health/conflicts/${encodeURIComponent(conflictId)}/resolve`);
}

// -- Ask (🔒 AI-gated) ------------------------------------------------------------

export function ask(petId: string, body: AskRequest): Promise<QAAnswer> {
  return apiPost<QAAnswer>(`${petPath(petId)}/ask`, body);
}

// -- Audit (free) -----------------------------------------------------------------

export function auditTrail(limit = 50): Promise<AuditEntryRead[]> {
  return apiGet<AuditEntryRead[]>(`/api/health/audit?limit=${limit}`);
}
