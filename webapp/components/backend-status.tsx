"use client";

import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";

/** Polls the read-API health probe; renders a loud banner when it's down so a
 *  dead backend can never masquerade as "no data" (bit us once). */
export function BackendStatus() {
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

  if (state === "ok") return null;
  return (
    <div className="border-b border-danger/40 bg-danger/15 px-8 py-2 text-[12.5px] font-medium text-danger">
      {state === "api_down"
        ? "Backend offline — the read-API is not responding. Pages will show empty data until it is back (./cm ui restarts it)."
        : "Database unreachable — the API is up but Postgres is not responding (docker compose up -d)."}
    </div>
  );
}
