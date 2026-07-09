const SERVER_BASE = process.env.API_BASE ?? "http://127.0.0.1:8400/api/v1";

export function apiBase(): string {
  return typeof window === "undefined" ? SERVER_BASE : "/api/v1";
}

/** GET that never throws page-breaking errors: returns fallback on any failure. */
export async function get<T>(path: string, fallback: T): Promise<T> {
  try {
    const res = await fetch(`${apiBase()}${path}`, { cache: "no-store" });
    if (!res.ok) {
      // Soft-fail by design, but never silently: a failing endpoint would
      // otherwise be indistinguishable from a genuinely empty window.
      console.error(`[api] GET ${path} -> ${res.status}`);
      return fallback;
    }
    return (await res.json()) as T;
  } catch (e) {
    console.error(`[api] GET ${path} unreachable:`, e);
    return fallback;
  }
}

export async function post(
  path: string,
  body: unknown,
): Promise<{ ok: boolean; status: number; detail?: string }> {
  try {
    const res = await fetch(`${apiBase()}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    let detail: string | undefined;
    if (!res.ok) {
      try {
        const j = await res.json();
        detail = typeof j?.detail === "string" ? j.detail : JSON.stringify(j);
      } catch {
        /* ignore */
      }
    }
    return { ok: res.ok, status: res.status, detail };
  } catch (e) {
    return { ok: false, status: 0, detail: String(e) };
  }
}
