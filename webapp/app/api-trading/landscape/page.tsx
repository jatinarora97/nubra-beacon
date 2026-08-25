import { PageHeader } from "@/components/ui";
import { DaysFilter } from "../days-filter";
import { pickDays } from "../lens";
import { LandscapeManager } from "./landscape-manager";

export default async function ApiTradingLandscapePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const days = pickDays(await searchParams);
  return (
    <div>
      <PageHeader
        title="API-trading landscape"
        accent="bg-warn"
        blurb="Who API traders talk about and what those players ship: live mention coverage per competitor over the window, plus a feature catalog kept fresh by a weekly monitor and manual adds."
      />
      <DaysFilter days={days} />
      <LandscapeManager days={days} />
    </div>
  );
}
