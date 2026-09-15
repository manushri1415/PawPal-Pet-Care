/**
 * The visitor's session (api/routers/session.py): a private demo sandbox, or
 * the owner space when an owner key is set.
 *
 * `["session"]` is fetched first, before any other query (see SessionGate):
 * the first API request of a visit creates the sandbox and its cookie, and if
 * the page's parallel queries went first, each would create a sandbox of its
 * own.
 */

import { apiGet, apiPost } from "./client";

export interface SessionInfo {
  kind: "demo" | "owner";
  /** ISO datetime (UTC) when the demo sandbox is deleted; null for the owner space. */
  expires_at: string | null;
}

export const SESSION_QUERY_KEY = ["session"] as const;

export function getSession(): Promise<SessionInfo> {
  return apiGet<SessionInfo>("/api/session");
}

/** Wipe this visitor's sandbox and start again from the demo data. */
export function resetDemo(): Promise<SessionInfo> {
  return apiPost<SessionInfo>("/api/session/reset");
}
