/**
 * Thin fetch wrapper for the FastAPI backend. All calls use relative `/api/...`
 * paths: the Vite dev server proxies these to uvicorn (see vite.config.ts),
 * and in production api/main.py serves this app from the same origin — so no
 * base URL and no CORS handling are ever needed.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}
