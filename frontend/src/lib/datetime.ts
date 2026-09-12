/**
 * Shared datetime helpers so every form/list formats and parses dates the
 * same way instead of each component reinventing (and risking a subtly
 * different) `datetime-local` <-> ISO conversion.
 */

/** ISO datetime (from the API) -> value for an `<input type="datetime-local">`. */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** `<input type="datetime-local">` value -> ISO datetime string for the API. */
export function localInputToIso(value: string): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return undefined;
  return d.toISOString();
}

/** Parse a bare "YYYY-MM-DD" calendar date (no time-of-day, e.g. a
 * Reminder's `due_date`) as LOCAL midnight instead of the `Date` constructor's
 * default of treating a date-only string as UTC midnight -- which renders a
 * day early in any timezone behind UTC. Returns null for anything else (a
 * full datetime, say), so callers fall back to `new Date(value)` for those. */
export function parseDateOnly(value: string | null | undefined): Date | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const [, year, month, day] = match;
  return new Date(Number(year), Number(month) - 1, Number(day));
}

/** ISO datetime (or bare date) -> "Sep 12, 2026" for compact display in lists. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = parseDateOnly(iso) ?? new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

/** ISO datetime -> "2:30 PM" for compact display in schedule rows. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
