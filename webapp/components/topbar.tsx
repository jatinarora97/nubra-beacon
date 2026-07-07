import { SettingsMenu } from "@/components/theme";

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
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-opps" />
          beacon live
        </div>
        <SettingsMenu />
      </div>
    </header>
  );
}
