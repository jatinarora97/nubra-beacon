import { SettingsMenu } from "@/components/theme";
import { HealthDot } from "@/components/health-dot";

export function Topbar() {
  const now = new Date().toLocaleDateString("en-IN", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "Asia/Kolkata",
  });
  return (
    <header className="flex h-14 items-center justify-between border-b border-line bg-surface/60 px-8 backdrop-blur">
      <div className="text-[13px] text-muted">{now} · IST</div>
      <div className="flex items-center gap-4">
        <HealthDot />
        <SettingsMenu />
      </div>
    </header>
  );
}
