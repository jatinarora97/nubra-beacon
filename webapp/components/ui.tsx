import type { ReactNode } from "react";

export function SectionCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-[10px] border border-line bg-surface p-5 ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  accent,
  blurb,
}: {
  title: string;
  accent: string; // tailwind bg-* class
  blurb: string;
}) {
  return (
    <div className="mb-7">
      <div className="flex items-center gap-2.5">
        <span className={`h-2 w-2 rounded-full ${accent}`} />
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      </div>
      <p className="mt-1.5 max-w-2xl text-[13.5px] leading-relaxed text-muted">
        {blurb}
      </p>
    </div>
  );
}

export function KpiCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-[10px] border border-line bg-surface px-4 py-3">
      <div className="micro">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-[11.5px] text-muted">{hint}</div>}
    </div>
  );
}

const BADGE_STYLES: Record<string, string> = {
  trends: "border-trends/40 text-trends",
  danger: "border-danger/40 text-danger",
  warn: "border-warn/40 text-warn",
  opps: "border-opps/40 text-opps",
  content: "border-content/40 text-content",
  voices: "border-voices/40 text-voices",
  muted: "border-line text-muted",
};

export function Badge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: keyof typeof BADGE_STYLES;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-md border bg-surface2/50 px-2 py-0.5 text-[11px] font-medium tracking-wide ${BADGE_STYLES[tone]}`}
    >
      {children}
    </span>
  );
}

export function StatInline({
  label,
  value,
  tip,
}: {
  label: string;
  value: ReactNode;
  tip?: string;
}) {
  return (
    <span className="inline-flex items-baseline gap-1.5 text-[12.5px]">
      <span
        className={`text-muted ${tip ? "cursor-help underline decoration-dotted decoration-muted/50 underline-offset-2" : ""}`}
        title={tip}
      >
        {label}
      </span>
      <span className="font-medium tabular-nums text-ink">{value}</span>
    </span>
  );
}

export function EmptyState({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[10px] border border-dashed border-line bg-surface/50 px-6 py-8 text-center">
      <div className="text-[13.5px] font-medium text-ink">{title}</div>
      <div className="mx-auto mt-1 max-w-md text-[12.5px] leading-relaxed text-muted">
        {body}
      </div>
    </div>
  );
}

export function InfoTip({ text }: { text: string }) {
  return (
    <span
      title={text}
      className="ml-1 inline-flex h-3.5 w-3.5 cursor-help items-center justify-center rounded-full border border-line text-[9px] text-muted"
    >
      i
    </span>
  );
}
