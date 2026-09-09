import { PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { windowQuery } from "@/lib/window";
import { pickLensWindow } from "../lens";
import { LandscapeManager } from "./landscape-manager";

export default async function ApiTradingLandscapePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const w = pickLensWindow(await searchParams);
  return (
    <div>
      <PageHeader
        title="API-trading landscape"
        accent="bg-warn"
        blurb="Who API traders talk about and what those players ship: live mention coverage per competitor over the window, plus a feature catalog kept fresh by a weekly monitor and manual adds."
      />
      <TimeFilter current={w} />
      <LandscapeManager windowQS={windowQuery(w)} />
    </div>
  );
}
