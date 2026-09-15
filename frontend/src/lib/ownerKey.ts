/**
 * sessionStorage-backed holder for the PawPal owner key (see
 * MIGRATION_PLAN.md §4). Deliberately sessionStorage, not localStorage — the
 * key should disappear when the browser tab/session closes rather than
 * persist indefinitely. `OwnerKeyGate` writes it; `api/health.ts` reads it to
 * attach the `X-PawPal-Owner-Key` header on the two AI-gated calls.
 */

const STORAGE_KEY = "pp-owner-key";
const HEADER_NAME = "X-PawPal-Owner-Key";

export function getOwnerKey(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // sessionStorage unavailable (privacy mode, etc.) — treat as no key set
  }
}

export function setOwnerKey(key: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, key);
  } catch {
    /* ignore — the key just won't persist for this session */
  }
}

export function clearOwnerKey(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function hasOwnerKey(): boolean {
  return !!getOwnerKey();
}

/** Headers to attach to a gated request — empty object when no key is set,
 * so the backend still answers (with 401/503) rather than the frontend
 * silently swallowing the call. */
export function ownerKeyHeaders(): Record<string, string> {
  const key = getOwnerKey();
  return key ? { [HEADER_NAME]: key } : {};
}
