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

const pad2 = (n: number) => String(n).padStart(2, "0");

/** A Date -> timezone-less local ISO datetime, "2026-09-15T20:05:00". */
function toLocalIso(d: Date): string {
  return (
    `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}` +
    `T${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`
  );
}

/** The browser's current local wall-clock time, timezone-less. Sent with every
 * API request so the server can use the visitor's "today" (api/clock.py). */
export function localNowIso(now = new Date()): string {
  return toLocalIso(now);
}

/** `<input type="datetime-local">` value -> ISO datetime string for the API.
 *
 * Deliberately local and timezone-less, not `toISOString()` (UTC): the
 * scheduler works in the owner's wall-clock time — a task's preferred time is
 * "08:30" in their day — so a weekly task created for Monday evening must stay
 * a Monday task, not become the Tuesday it already is in UTC. */
export function localInputToIso(value: string): string | undefined {
  if (!value) return undefined;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return undefined;
  return toLocalIso(d);
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

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
}

/** Whole calendar days from today to `iso` (negative = past), or null if unparseable. */
export function dayOffsetFromToday(iso: string | null | undefined, now = new Date()): number | null {
  if (!iso) return null;
  const d = parseDateOnly(iso) ?? new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return Math.round((startOfDay(d) - startOfDay(now)) / 86_400_000);
}

/** ISO datetime -> "Today" / "Tomorrow" / "Yesterday" / "Sep 20" (year only when not this year). */
export function formatRelativeDay(iso: string | null | undefined, now = new Date()): string {
  const offset = dayOffsetFromToday(iso, now);
  if (offset === null) return "";
  if (offset === 0) return "Today";
  if (offset === 1) return "Tomorrow";
  if (offset === -1) return "Yesterday";
  const d = parseDateOnly(iso) ?? new Date(iso as string);
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }),
  });
}

/** A task's "HH:MM" preferred time -> "2:30 PM"; returns the input unchanged if it isn't HH:MM. */
export function formatClockTime(value: string): string {
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return value;
  const d = new Date();
  d.setHours(Number(match[1]), Number(match[2]), 0, 0);
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** ISO datetime -> "2:30 PM" for compact display in schedule rows. */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
