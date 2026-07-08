"use client";

import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";

/** Topbar status wired to the real /health probe (not decorative). */
export function HealthDot() {
  const [state, setState] = useState<"ok" | "api_down" | "db_down">("ok");

  useEffect(() => {
    let alive = true;
    async function probe() {
      try {
        const res = await fetch(`${apiBase()}/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(String(res.status));
        const j = await res.json();
        if (alive) setState(j.db ? "ok" : "db_down");
      } catch {
        if (alive) setState("api_down");
      }
    }
    probe();
    const t = setInterval(probe, 20_000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const meta = {
    ok: { dot: "bg-opps", label: "beacon live" },
    db_down: { dot: "bg-warn", label: "database unreachable" },
    api_down: { dot: "bg-danger", label: "backend offline" },
  }[state];

  return (
    <div className="flex items-center gap-2 text-[12px] text-muted">
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </div>
  );
}
