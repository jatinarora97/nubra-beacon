"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import { apiBase, post } from "@/lib/api";

type AccessRequest = {
  email: string;
  status: "approved" | "pending" | "rejected";
  requested_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
};

function fmtIst(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

const STATUS_TONE: Record<AccessRequest["status"], "opps" | "warn" | "danger"> = {
  approved: "opps",
  pending: "warn",
  rejected: "danger",
};

export function AccessRequestsManager() {
  const [rows, setRows] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/sso/requests`, { cache: "no-store" });
      if (res.ok) setRows(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function decide(email: string, status: "approved" | "rejected") {
    if (busy) return;
    setBusy(email);
    try {
      const res = await post(
        `/sso/requests/${encodeURIComponent(email)}/decide`,
        { status },
      );
      if (!res.ok) {
        setMsg(res.detail ?? "Could not record the decision.");
        setTimeout(() => setMsg(null), 4000);
      }
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  async function remove(email: string) {
    // Two-click confirm: first click arms the button, second click deletes.
    if (confirming !== email) {
      setConfirming(email);
      setTimeout(() => setConfirming((c) => (c === email ? null : c)), 4000);
      return;
    }
    setConfirming(null);
    if (busy) return;
    setBusy(email);
    try {
      // lib/api has no DELETE helper — plain fetch against apiBase().
      const res = await fetch(
        `${apiBase()}/sso/requests/${encodeURIComponent(email)}`,
        { method: "DELETE" },
      );
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        setMsg(
          typeof d?.detail === "string" ? d.detail : "Could not remove the entry.",
        );
        setTimeout(() => setMsg(null), 4000);
      }
      await refresh();
    } finally {
      setBusy(null);
    }
  }

  const pending = rows.filter((r) => r.status === "pending");
  const decided = rows.filter((r) => r.status !== "pending");

  if (loading) {
    return (
      <EmptyState title="Loading requests" body="Fetching the sign-in allowlist." />
    );
  }

  return (
    <div className="space-y-6">
      {msg && <p className="text-[12.5px] text-danger">{msg}</p>}

      <SectionCard>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
          Pending ({pending.length})
        </h2>
        {pending.length === 0 ? (
          <p className="text-[12.5px] text-muted">
            No one is waiting for access right now.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left">
                  {["email", "requested", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {pending.map((r) => (
                  <tr key={r.email}>
                    <td className="px-2 py-2 text-[13px] text-ink">{r.email}</td>
                    <td className="px-2 py-2 text-[12px] tabular-nums">
                      {fmtIst(r.requested_at)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => decide(r.email, "approved")}
                          disabled={busy !== null}
                          className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-opps hover:text-opps disabled:opacity-50"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => decide(r.email, "rejected")}
                          disabled={busy !== null}
                          className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-danger hover:text-danger disabled:opacity-50"
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {decided.length > 0 && (
        <SectionCard>
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
            Decided ({decided.length})
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left">
                  {["email", "status", "decided by", "decided", ""].map((h, i) => (
                    <th
                      key={i}
                      className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {decided.map((r) => (
                  <tr key={r.email}>
                    <td className="px-2 py-2 text-[13px] text-ink">{r.email}</td>
                    <td className="px-2 py-2">
                      <Badge tone={STATUS_TONE[r.status]}>{r.status}</Badge>
                    </td>
                    <td className="px-2 py-2 text-[12.5px] text-muted">
                      {r.decided_by ?? "—"}
                    </td>
                    <td className="px-2 py-2 text-[12px] tabular-nums">
                      {fmtIst(r.decided_at)}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <button
                        onClick={() => remove(r.email)}
                        disabled={busy !== null}
                        className={`rounded-md border px-2.5 py-1 text-[11.5px] transition-colors disabled:opacity-50 ${
                          confirming === r.email
                            ? "border-danger text-danger"
                            : "border-line text-muted hover:border-danger hover:text-danger"
                        }`}
                      >
                        {confirming === r.email ? "Confirm remove" : "Remove"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}
