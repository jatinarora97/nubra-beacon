"use client";

import { useState, type ReactNode } from "react";

export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setDone(true);
        setTimeout(() => setDone(false), 1500);
      }}
      className="rounded-md border border-line bg-surface2 px-2.5 py-1 text-[11.5px] font-medium text-muted transition-colors hover:border-muted hover:text-ink"
    >
      {done ? "Copied" : label}
    </button>
  );
}

export function Tabs({
  tabs,
}: {
  tabs: { label: string; content: ReactNode }[];
}) {
  const [active, setActive] = useState(0);
  return (
    <div>
      <div className="flex gap-1 border-b border-line">
        {tabs.map((t, i) => (
          <button
            key={t.label}
            onClick={() => setActive(i)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-[12.5px] font-medium transition-colors ${
              i === active
                ? "border-ink text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="pt-3">{tabs[active]?.content}</div>
    </div>
  );
}

export function Expandable({
  summary,
  children,
}: {
  summary: ReactNode;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between rounded-md px-1 py-1 text-left text-[13px] text-ink hover:bg-surface2/50"
      >
        {summary}
        <span className="ml-2 text-[11px] text-muted">{open ? "hide" : "show"}</span>
      </button>
      {open && <div className="mt-2">{children}</div>}
    </div>
  );
}
