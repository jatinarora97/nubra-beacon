"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import type { Opportunity } from "@/lib/types";
import { DISMISS_REASONS } from "@/lib/types";
import { Badge, SectionCard, StatInline } from "@/components/ui";
import { CopyButton, Tabs } from "@/components/client";

export function OpportunityCard({
  opp,
  rank,
}: {
  opp: Opportunity;
  rank: number;
}) {
  const [status, setStatus] = useState(opp.status);
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState<string>("");
  const [err, setErr] = useState<string>("");

  async function act(newStatus: "acted" | "dismissed") {
    setErr("");
    const body: Record<string, string> = { status: newStatus };
    if (newStatus === "dismissed") {
      if (!reason) {
        setErr("Pick a dismissal reason first.");
        return;
      }
      body.dismissed_reason = reason;
    }
    const prev = status;
    setStatus(newStatus); // optimistic
    const res = await post(`/opportunities/${opp.id}/status`, body);
    if (!res.ok) {
      setStatus(prev);
      setErr(
        res.status === 409
          ? "Already resolved by someone else — refresh to see the latest."
          : res.detail || `Failed (${res.status}).`,
      );
    } else {
      setDismissing(false);
    }
  }

  const resolved = status !== "suggested";

  return (
    <SectionCard className={resolved ? "opacity-55" : ""}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <span className="text-[15px] font-semibold">Priority {rank}</span>
          <Badge tone="opps">{opp.kind_label ?? opp.kind ?? "action"}</Badge>
          <span className="text-[11.5px] text-muted">score {opp.priority}/100</span>
          {resolved && <Badge>{status}</Badge>}
        </div>
        {!resolved && (
          <div className="flex shrink-0 items-center gap-2">
            <button
              onClick={() => act("acted")}
              className="rounded-md border border-line px-3 py-1 text-[12px] font-medium text-muted transition-colors hover:border-opps hover:text-opps"
            >
              Mark acted
            </button>
            <button
              onClick={() => setDismissing(!dismissing)}
              className="rounded-md border border-line px-3 py-1 text-[12px] font-medium text-muted transition-colors hover:border-danger hover:text-danger"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {dismissing && !resolved && (
        <div className="mt-3 flex items-center gap-2 rounded-md border border-line bg-surface2/60 p-2.5">
          <select
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="rounded-md border border-line bg-surface px-2 py-1 text-[12.5px]"
          >
            <option value="">why dismiss?</option>
            {DISMISS_REASONS.map((r) => (
              <option key={r} value={r}>
                {r.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <button
            onClick={() => act("dismissed")}
            className="rounded-md border border-danger/50 px-3 py-1 text-[12px] font-medium text-danger hover:bg-danger/10"
          >
            Confirm dismiss
          </button>
        </div>
      )}
      {err && <p className="mt-2 text-[12px] text-danger">{err}</p>}

      {opp.why_engage && (
        <p className="mt-3 text-[13.5px] leading-relaxed">{opp.why_engage}</p>
      )}
      {opp.title && (
        <p className="mt-1.5 text-[12.5px] italic leading-relaxed text-muted">
          “{opp.title}”
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line pt-3">
        <StatInline
          label="engagement"
          value={opp.interactions ?? "n/a"}
          tip="Real interactions on the thread: likes + replies + shares."
        />
        <StatInline
          label="age"
          value={opp.age_h != null ? `${Math.round(opp.age_h)}h` : "n/a"}
        />
        {opp.when_window && (
          <StatInline
            label="post window"
            value={`${opp.when_action ?? ""} ${opp.when_window}`.trim()}
            tip={opp.when_why}
          />
        )}
        {opp.url && (
          <a
            href={opp.url}
            target="_blank"
            className="ml-auto text-[12.5px] text-trends hover:underline"
          >
            open thread
          </a>
        )}
      </div>

      {(opp.brand_reply || opp.rep_reply) && (
        <div className="mt-3">
          <Tabs
            tabs={[
              opp.brand_reply
                ? {
                    label: "Brand draft",
                    content: (
                      <DraftBlock text={opp.brand_reply} kind="official Nubra voice" />
                    ),
                  }
                : null,
              opp.rep_reply
                ? {
                    label: "Rep draft",
                    content: (
                      <DraftBlock
                        text={opp.rep_reply}
                        kind="human, discloses Nubra affiliation"
                      />
                    ),
                  }
                : null,
            ].filter(Boolean) as { label: string; content: React.ReactNode }[]}
          />
        </div>
      )}
    </SectionCard>
  );
}

function DraftBlock({ text, kind }: { text: string; kind: string }) {
  return (
    <div className="rounded-md border border-line bg-surface2/50 p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="micro">{kind}</span>
        <CopyButton text={text} />
      </div>
      <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{text}</p>
    </div>
  );
}
