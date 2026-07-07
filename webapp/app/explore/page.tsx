import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { ExploreTable } from "./explore-table";

export default function ExplorePage() {
  return (
    <div>
      <PageHeader
        title="Explore the raw data"
        accent="bg-voices"
        blurb="The verification layer: inspect exactly what Beacon saw before it became a trend, issue or action. Engagement numbers are a snapshot at fetch time — threads that became action candidates get refreshed; the rest stay as first seen."
      />
      {/* Suspense: ExploreTable reads useSearchParams (?q= deep-links) */}
      <Suspense>
        <ExploreTable />
      </Suspense>
    </div>
  );
}
