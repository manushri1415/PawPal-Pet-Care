/**
 * Thin fetch wrapper for the FastAPI backend. All calls use relative `/api/...`
 * paths: the Vite dev server proxies these to uvicorn (see vite.config.ts),
 * and in production api/main.py serves this app from the same origin — so no
 * base URL and no CORS handling are ever needed.
 *
 * Every request carries the browser's local wall-clock time
 * (`X-PawPal-Client-Now`). The server's own clock is UTC in production, so it
 * cannot tell what "today" is for the person using the app; the backend reads
 * this header wherever a date is user-facing (see api/clock.py).
 *
 * Every request also carries the owner key when one is set
 * (`X-PawPal-Owner-Key`, see lib/ownerKey.ts): the key decides which space the
 * whole app reads and writes — the owner's own, or this browser's demo
 * sandbox — so it cannot be attached to only some calls. The sandbox itself is
 * identified by an HttpOnly cookie the browser sends on its own.
 */

import { localNowIso } from "../lib/datetime";
import { ownerKeyHeaders } from "../lib/ownerKey";

const CLIENT_NOW_HEADER = "X-PawPal-Client-Now";

/** Thrown for any non-2xx response; carries the HTTP status so callers can
 * branch on specific codes (e.g. a 409 pet-delete conflict, or a future 401
 * from the Phase 4 AI-gate) instead of string-matching the message. */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function withClientHeaders(headers?: Record<string, string>): Record<string, string> {
  return { [CLIENT_NOW_HEADER]: localNowIso(), ...ownerKeyHeaders(), ...headers };
}

async function handle<T>(res: Response, method: string, path: string): Promise<T> {
  if (!res.ok) {
    let detail: unknown;
    try {
      const body = await res.json();
      detail = body?.detail;
    } catch {
      /* no/invalid JSON body */
    }
    const suffix = detail !== undefined ? `: ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : "";
    throw new ApiError(`${method} ${path} failed: ${res.status}${suffix}`, res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: withClientHeaders() });
  return handle<T>(res, "GET", path);
}

export async function apiPost<T>(
  path: string,
  body?: unknown,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: withClientHeaders(
      body !== undefined ? { "Content-Type": "application/json", ...headers } : headers,
    ),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handle<T>(res, "POST", path);
}

/** POST a multipart/form-data body (e.g. a file upload) — used only by the
 * document-extraction endpoint. No Content-Type header is set explicitly;
 * the browser fills in the multipart boundary itself. */
export async function apiPostForm<T>(
  path: string,
  form: FormData,
  headers?: Record<string, string>,
): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: withClientHeaders(headers), body: form });
  return handle<T>(res, "POST", path);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "PATCH",
    headers: withClientHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  return handle<T>(res, "PATCH", path);
}

export async function apiDelete<T = void>(path: string): Promise<T> {
  const res = await fetch(path, { method: "DELETE", headers: withClientHeaders() });
  return handle<T>(res, "DELETE", path);
}
