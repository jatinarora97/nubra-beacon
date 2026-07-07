"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NubraMark } from "@/components/logo";

const NAV: { href: string; label: string; dot: string; group?: string }[] = [
  { href: "/", label: "Overview", dot: "bg-muted" },
  { href: "/trends", label: "Trends", dot: "bg-trends", group: "What's happening" },
  { href: "/issues", label: "Broker issues", dot: "bg-danger" },
  { href: "/features", label: "Feature requests", dot: "bg-warn" },
  { href: "/nubra", label: "Nubra mentions", dot: "bg-opps" },
  { href: "/weekly", label: "Weekly roundup", dot: "bg-trends" },
  { href: "/opportunities", label: "Opportunities", dot: "bg-opps", group: "What to do" },
  { href: "/content", label: "Content briefs", dot: "bg-content", group: "What to make" },
  { href: "/voices", label: "Voices", dot: "bg-voices", group: "Who matters" },
  { href: "/explore", label: "Explore data", dot: "bg-muted", group: "Verify" },
  { href: "/sources", label: "Sources", dot: "bg-muted", group: "Configure" },
  { href: "/requests", label: "Beacon requests", dot: "bg-content", group: "Improve" },
];

export function Sidebar() {
  const path = usePathname();
  let lastGroup: string | undefined;
  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line bg-surface px-4 py-6 md:flex">
      <Link href="/" className="mb-8 block px-2">
        <div className="flex items-center gap-2.5">
          <NubraMark className="h-[18px] w-6 shrink-0 text-ink" />
          <div className="text-[15px] font-semibold tracking-tight">
            Nubra <span className="text-muted">Beacon</span>
          </div>
        </div>
        <div className="micro mt-1.5">listen · understand · recommend</div>
      </Link>
      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map((n) => {
          const showGroup = n.group && n.group !== lastGroup;
          lastGroup = n.group ?? lastGroup;
          const active = path === n.href;
          return (
            <div key={n.href}>
              {showGroup && <div className="micro mt-5 mb-1.5 px-2">{n.group}</div>}
              <Link
                href={n.href}
                className={`flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-[13.5px] transition-colors ${
                  active
                    ? "bg-surface2 font-medium text-ink"
                    : "text-muted hover:bg-surface2/60 hover:text-ink"
                }`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${n.dot}`} />
                {n.label}
              </Link>
            </div>
          );
        })}
      </nav>
      <div className="micro px-2">v1 · internal</div>
    </aside>
  );
}
