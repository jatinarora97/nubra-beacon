"use client";

import { useState } from "react";
import { Badge, SectionCard } from "@/components/ui";
import { CopyButton } from "@/components/client";
import { apiBase } from "@/lib/api";
import type { Proposal } from "@/lib/types";

const inputCls =
  "w-full rounded-[10px] border border-line bg-surface2 px-3 py-2 text-[13px] text-ink outline-none focus:border-content";

type Editable = {
  hook: string;
  caption: string;
  cta: string;
  beats: string; // newline-separated in the editor
  platform: string;
};

function toEditable(p: Proposal): Editable {
  return {
    hook: p.hook ?? "",
    caption: p.caption ?? "",
    cta: p.cta ?? "",
    beats: (p.beats ?? []).join("\n"),
    platform: p.platform ?? "",
  };
}

export function ProposalCard({ initial, platforms }: { initial: Proposal; platforms: string[] }) {
  const [p, setP] = useState<Proposal>(initial);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Editable>(toEditable(initial));
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function apply() {
    if (busy) return;
    setBusy(true);
    setErr(null);
    const manual: Record<string, unknown> = {};
    const base = toEditable(p);
    if (draft.hook !== base.hook) manual.hook = draft.hook;
    if (draft.caption !== base.caption) manual.caption = draft.caption;
    if (draft.cta !== base.cta) manual.cta = draft.cta;
    if (draft.beats !== base.beats)
      manual.beats = draft.beats.split("\n").map((b) => b.trim()).filter(Boolean);
    const body: Record<string, unknown> = { day: p.day, rank: p.rank };
    if (Object.keys(manual).length) body.manual = manual;
    if (draft.platform && draft.platform !== p.platform) body.platform = draft.platform;
    if (instruction.trim()) body.instruction = instruction.trim();
    if (!body.manual && !body.platform && !body.instruction) {
      setBusy(false);
      setEditing(false);
      return;
    }
    try {
      const res = await fetch(`${apiBase()}/content-proposals/revise`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await res.json();
      if (!res.ok) {
        setErr(typeof d?.detail === "string" ? d.detail : "Revision failed.");
      } else {
        setP(d);
        setDraft(toEditable(d));
        setInstruction("");
        setEditing(false);
      }
    } catch {
      setErr("Backend unreachable.");
    }
    setBusy(false);
  }

  return (
    <SectionCard>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="micro mb-1">brief {p.rank}</div>
          <h3 className="text-[15px] font-semibold leading-snug">
            {p.treatment ?? p.format_family ?? "Untitled brief"}
          </h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {p.platform && <Badge tone="content">{p.platform.replace(/_/g, " ")}</Badge>}
          {p.format_family && <Badge>{p.format_family.replace(/_/g, " ")}</Badge>}
          {p.window && <Badge>post {p.window}</Badge>}
          <button
            onClick={() => {
              setDraft(toEditable(p));
              setErr(null);
              setEditing((e) => !e);
            }}
            className="rounded-md border border-line px-2.5 py-1 text-[11.5px] text-muted transition-colors hover:border-content hover:text-ink"
          >
            {editing ? "Cancel" : "Edit"}
          </button>
        </div>
      </div>

      {p.platform_why && !editing && (
        <p className="mt-1.5 text-[12.5px] text-muted">Why this platform: {p.platform_why}</p>
      )}

      {!editing ? (
        <>
          {p.hook && (
            <blockquote className="mt-3 border-l-2 border-content/60 pl-3 text-[14px] font-medium leading-relaxed">
              {p.hook}
            </blockquote>
          )}

          {(p.beats?.length ?? 0) > 0 && (
            <div className="mt-4">
              <div className="micro mb-2">production checklist</div>
              <ol className="space-y-1.5">
                {p.beats!.map((b, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed">
                    <span className="mt-px shrink-0 text-[11.5px] font-semibold tabular-nums text-content">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span>{b}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {(p.caption || (p.hashtags?.length ?? 0) > 0 || p.cta) && (
            <div className="mt-4 rounded-md border border-line bg-surface2/50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <span className="micro">ready to paste</span>
                <CopyButton
                  text={[p.caption, (p.hashtags ?? []).join(" "), p.cta]
                    .filter(Boolean)
                    .join("\n\n")}
                  label="Copy caption kit"
                />
              </div>
              {p.caption && <p className="text-[13px] leading-relaxed">{p.caption}</p>}
              {(p.hashtags?.length ?? 0) > 0 && (
                <p className="mt-1.5 text-[12.5px] text-trends">{p.hashtags!.join(" ")}</p>
              )}
              {p.cta && <p className="mt-1.5 text-[12.5px] text-muted">CTA: {p.cta}</p>}
            </div>
          )}

          <div className="mt-3 flex flex-col gap-1 border-t border-line pt-3 text-[12.5px] text-muted">
            {p.visual_direction && <span>Visual direction: {p.visual_direction}</span>}
            {p.why && <span>Why now: {p.why}</span>}
            {(p.revisions_count ?? 0) > 0 && (
              <span>
                revised {p.revisions_count} time{p.revisions_count !== 1 ? "s" : ""}
                {p.last_revised_by && ` · last by ${p.last_revised_by}`}
              </span>
            )}
          </div>
        </>
      ) : (
        <div className="mt-4 space-y-3">
          <div>
            <div className="micro mb-1.5">hook</div>
            <textarea
              value={draft.hook}
              onChange={(e) => setDraft({ ...draft, hook: e.target.value })}
              rows={2}
              className={`${inputCls} resize-y`}
            />
          </div>
          <div>
            <div className="micro mb-1.5">production checklist (one beat per line)</div>
            <textarea
              value={draft.beats}
              onChange={(e) => setDraft({ ...draft, beats: e.target.value })}
              rows={5}
              className={`${inputCls} resize-y`}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <div className="micro mb-1.5">caption</div>
              <textarea
                value={draft.caption}
                onChange={(e) => setDraft({ ...draft, caption: e.target.value })}
                rows={3}
                className={`${inputCls} resize-y`}
              />
            </div>
            <div className="space-y-3">
              <div>
                <div className="micro mb-1.5">cta</div>
                <input
                  value={draft.cta}
                  onChange={(e) => setDraft({ ...draft, cta: e.target.value })}
                  className={inputCls}
                />
              </div>
              <div>
                <div className="micro mb-1.5">platform (changing re-tailors via Beacon)</div>
                <select
                  value={draft.platform}
                  onChange={(e) => setDraft({ ...draft, platform: e.target.value })}
                  className={inputCls}
                >
                  {platforms.map((pl) => (
                    <option key={pl} value={pl}>
                      {pl.replace(/_/g, " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div>
            <div className="micro mb-1.5">tell Beacon what to change (optional)</div>
            <input
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && apply()}
              placeholder="e.g. tighten the hook, make the caption less formal, add a stat beat"
              className={inputCls}
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={apply}
              disabled={busy}
              className="rounded-[10px] border border-content/50 bg-content/10 px-4 py-2 text-[13px] font-semibold text-content transition-colors hover:bg-content/20 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? "Revising…" : "Apply"}
            </button>
            <span className="text-[12px] text-muted">
              {busy
                ? "Beacon is revising — instructions and platform changes take a few seconds."
                : "Manual edits apply directly; instructions and platform changes go through Beacon and re-check compliance."}
            </span>
            {err && <span className="text-[12px] text-danger">{err}</span>}
          </div>
        </div>
      )}
    </SectionCard>
  );
}
