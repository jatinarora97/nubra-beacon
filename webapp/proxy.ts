import { NextResponse, type NextRequest } from "next/server";

// SSO authorization gate. oauth2-proxy (Google) fronts the webapp on prod and
// forwards the verified email in x-auth-request-email; we check it against the
// read-API allowlist. Local dev and pre-cutover prod have no proxy in front, so
// a missing header means SSO is a no-op and every request passes through.
//
// Next 16 note: the middleware.ts convention is deprecated and renamed to
// proxy.ts — same behavior, Node.js runtime (module-level cache persists).

const API_BASE = process.env.API_BASE ?? "http://127.0.0.1:8400/api/v1";
const CACHE_TTL_MS = 60_000;

// email -> last verdict. The authz endpoint has a side effect (unknown emails
// become pending + a Slack ping), so we deliberately call it at most once per
// TTL window per email, not once per asset/request.
const authzCache = new Map<string, { status: string; ts: number }>();

export async function proxy(request: NextRequest) {
  // oauth2-proxy sends the verified identity UPSTREAM as x-forwarded-email
  // (x-auth-request-email only appears on auth-endpoint responses) — accept both.
  const email = request.headers.get("x-auth-request-email")
    ?? request.headers.get("x-forwarded-email");
  if (!email) return NextResponse.next(); // no oauth2-proxy in front — SSO off

  const now = Date.now();
  const cached = authzCache.get(email);
  let status = cached && now - cached.ts < CACHE_TTL_MS ? cached.status : null;

  if (!status) {
    try {
      const res = await fetch(
        `${API_BASE}/sso/authz?email=${encodeURIComponent(email)}`,
      );
      if (!res.ok) {
        // Stale read-API without the route (404) or any other failure:
        // fail open — an authz hiccup must not brick the dashboard.
        console.error(`[sso] authz ${email} -> HTTP ${res.status}; failing open`);
        return NextResponse.next();
      }
      const body = (await res.json()) as { status?: string };
      status = body.status ?? "pending";
      authzCache.set(email, { status, ts: now });
    } catch (e) {
      console.error(`[sso] authz ${email} unreachable; failing open:`, e);
      return NextResponse.next();
    }
  }

  if (status === "approved") return NextResponse.next();
  return NextResponse.rewrite(new URL("/access-pending", request.url));
}

export const config = {
  // Everything except: Next internals, favicons/static assets, the pending page
  // itself, and the Slack interactivity webhook (Slack posts there without SSO
  // by design — it is verified by its own signature check in the read-API).
  matcher: [
    "/((?!_next/|favicon|access-pending|api/v1/slack/interactions|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|css|js|map|txt|woff2?)$).*)",
  ],
};
