import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { pickWindow } from "@/lib/window";
import { ExploreTable } from "./explore-table";

export default async function ExplorePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const w = pickWindow(await searchParams);
  return (
    <div>
      <PageHeader
        title="Explore the raw data"
        accent="bg-voices"
        blurb="The verification layer: inspect exactly what Beacon saw before it became a trend, issue or action. Engagement numbers are a snapshot at fetch time — threads that became action candidates get refreshed; the rest stay as first seen."
      />
      <TimeFilter current={w} />
      {/* Suspense: ExploreTable reads useSearchParams (?q= deep-links + window) */}
      <Suspense>
        <ExploreTable />
      </Suspense>
    </div>
  );
}
