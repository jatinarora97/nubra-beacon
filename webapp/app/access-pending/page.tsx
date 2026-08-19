import { headers } from "next/headers";

export const dynamic = "force-dynamic";

export default async function AccessPendingPage() {
  const email = (await headers()).get("x-auth-request-email");
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="max-w-md rounded-[10px] border border-line bg-surface px-8 py-10 text-center">
        <h1 className="text-xl font-semibold tracking-tight">Access pending</h1>
        <p className="mt-3 text-[13.5px] leading-relaxed text-muted">
          Your Google sign-in worked, but a Beacon admin has not approved your
          account yet. The team has been notified in Slack — approval usually
          takes a minute. Refresh this page after you hear back.
        </p>
        {email && (
          <p className="mt-4 text-[12px] text-muted">Signed in as {email}</p>
        )}
      </div>
    </div>
  );
}
