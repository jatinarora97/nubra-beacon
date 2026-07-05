"use client";

import { useEffect, useRef, useState } from "react";

type Mode = "system" | "dark" | "light";
const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "system", label: "System", hint: "follow the OS setting" },
  { value: "dark", label: "Dark", hint: "always dark" },
  { value: "light", label: "Light", hint: "always light" },
];

/** Runs before first paint (inlined in layout.tsx) so there is no theme flash. */
export const THEME_BOOT_SCRIPT = `(function(){try{var m=localStorage.getItem("theme")||"system";var t=m==="system"?(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark"):m;document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme="dark";}})();`;

function resolve(mode: Mode): "dark" | "light" {
  if (mode !== "system") return mode;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function apply(mode: Mode) {
  document.documentElement.dataset.theme = resolve(mode);
}

export function SettingsMenu() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<Mode>("system");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const stored = localStorage.getItem("theme") as Mode | null;
    if (stored === "dark" || stored === "light" || stored === "system") setMode(stored);
  }, []);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    const onChange = () => mode === "system" && apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [mode]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function pick(m: Mode) {
    setMode(m);
    localStorage.setItem("theme", m);
    apply(m);
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Settings"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-muted transition-colors hover:border-muted hover:text-ink"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-4 w-4"
          aria-hidden
        >
          <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 top-10 z-50 w-52 rounded-[10px] border border-line bg-surface p-1.5 shadow-lg shadow-black/20">
          <div className="micro px-2 pb-1 pt-1.5">Theme</div>
          {MODES.map((m) => {
            const active = mode === m.value;
            return (
              <button
                key={m.value}
                onClick={() => pick(m.value)}
                className={`flex w-full items-baseline justify-between rounded-lg px-2 py-1.5 text-left text-[13px] transition-colors ${
                  active ? "bg-surface2 font-medium text-ink" : "text-muted hover:bg-surface2/60 hover:text-ink"
                }`}
              >
                <span>{m.label}</span>
                <span className="text-[11px] text-muted">{active ? "active" : m.hint}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
