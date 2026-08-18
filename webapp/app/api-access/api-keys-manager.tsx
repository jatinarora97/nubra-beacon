"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, EmptyState, SectionCard } from "@/components/ui";
import { apiBase, post } from "@/lib/api";

type ApiKey = {
  key_id: string;
  label: string;
  created_by: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
};

type MintedKey = {
  key_id: string;
  label: string;
  created_at: string;
  secret: string;
  note?: string;
};

function fmtIst(value?: string | null): string {
  if (!value) return "never";
  return new Date(value).toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  });
}

export function ApiKeysManager() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [label, setLabel] = useState("");
  const [minted, setMinted] = useState<MintedKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [minting, setMinting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase()}/api-keys`, { cache: "no-store" });
      if (res.ok) setKeys(await res.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function mint() {
    if (!label.trim() || minting) return;
    setMinting(true);
    try {
      const res = await fetch(`${apiBase()}/api-keys`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim() }),
      });
      if (res.ok) {
        setMinted((await res.json()) as MintedKey);
        setCopied(false);
        setLabel("");
        refresh();
      } else {
        const d = await res.json().catch(() => ({}));
        setMsg(d.detail ?? "Could not create the key.");
        setTimeout(() => setMsg(null), 4000);
      }
    } finally {
      setMinting(false);
    }
  }

  async function copySecret() {
    if (!minted) return;
    await navigator.clipboard.writeText(minted.secret);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function revoke(keyId: string) {
    if (confirming !== keyId) {
      setConfirming(keyId);
      setTimeout(() => setConfirming((c) => (c === keyId ? null : c)), 4000);
      return;
    }
    setConfirming(null);
    const res = await post(`/api-keys/${keyId}/revoke`, {});
    if (!res.ok) {
      setMsg(res.detail ?? "Could not revoke the key.");
      setTimeout(() => setMsg(null), 4000);
    }
    refresh();
  }

  const inputCls =
    "rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-trends";

  return (
    <div className="space-y-6">
      <SectionCard>
        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
          Create a key
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && mint()}
            placeholder="who is this key for, e.g. growth-team-mcp"
            className={`${inputCls} w-80`}
          />
          <button
            onClick={mint}
            disabled={minting}
            className="rounded-[10px] border border-line bg-surface2 px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-trends disabled:opacity-50"
          >
            {minting ? "Creating..." : "Create key"}
          </button>
          {msg && <span className="text-[12.5px] text-muted">{msg}</span>}
        </div>
        {minted && (
          <div className="mt-4 rounded-[10px] border border-warn/40 bg-surface2/50 p-4">
            <div className="text-[12.5px] font-medium text-warn">
              Copy this secret now — it will never be shown again.
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <code className="rounded-md border border-line bg-surface px-3 py-2 font-mono text-[12.5px] break-all">
                {minted.secret}
              </code>
              <button
                onClick={copySecret}
                className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-trends hover:text-ink"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div className="mt-2 text-[12px] text-muted">
              Key &ldquo;{minted.label}&rdquo; ({minted.key_id}) — send it in the
              X-API-Key header. Beacon stores only a hash; if the secret is lost,
              revoke this key and create a new one.
            </div>
          </div>
        )}
      </SectionCard>

      {loading ? (
        <EmptyState title="Loading keys" body="Fetching the current API keys." />
      ) : keys.length === 0 ? (
        <EmptyState
          title="No API keys yet"
          body="Create one above to give a team or agent read access to the Beacon API."
        />
      ) : (
        <SectionCard>
          <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wider text-muted">
            Keys ({keys.filter((k) => !k.revoked_at).length} active)
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left">
                  {["label", "created by", "created", "last used", "status", ""].map(
                    (h, i) => (
                      <th
                        key={i}
                        className="px-2 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted"
                      >
                        {h}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {keys.map((k) => {
                  const revoked = Boolean(k.revoked_at);
                  return (
                    <tr key={k.key_id}>
                      <td
                        className={`px-2 py-2 text-[13px] ${revoked ? "text-muted line-through" : "text-ink"}`}
                      >
                        {k.label}
                      </td>
                      <td className="px-2 py-2 text-[12.5px] text-muted">
                        {k.created_by}
                      </td>
                      <td className="px-2 py-2 text-[12px] tabular-nums">
                        {fmtIst(k.created_at)}
                      </td>
                      <td className="px-2 py-2 text-[12px] tabular-nums">
                        {fmtIst(k.last_used_at)}
                      </td>
                      <td className="px-2 py-2">
                        <Badge tone={revoked ? "muted" : "opps"}>
                          {revoked ? "revoked" : "active"}
                        </Badge>
                      </td>
                      <td className="px-2 py-2 text-right">
                        {!revoked && (
                          <button
                            onClick={() => revoke(k.key_id)}
                            className={`rounded-md border px-2.5 py-1 text-[11.5px] transition-colors ${
                              confirming === k.key_id
                                ? "border-danger text-danger"
                                : "border-line text-muted hover:border-danger hover:text-danger"
                            }`}
                          >
                            {confirming === k.key_id ? "Confirm revoke" : "Revoke"}
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      <p className="text-[11.5px] leading-relaxed text-muted">
        Endpoints: /items, /items/search, /authors, /trends, /broker-issues,
        /feature-requests, /nubra-mentions, /opportunities, /drafts, /briefs,
        /roundups, /runs, /source-health, /watch-sources, /taxonomy, /grounding,
        /usage — all GET, JSON, cursor-paginated.
      </p>
    </div>
  );
}
