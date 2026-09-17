import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { ContentQueue } from "@/components/content-queue";
import { pickWindow } from "@/lib/window";
import { ProposalArchive } from "./proposal-archive";

export default async function ContentPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // defaultAll: the queue opens on every brief; chips narrow by created_at.
  const w = pickWindow(await searchParams, true);
  return (
    <div>
      <PageHeader
        title="Content briefs"
        accent="bg-content"
        blurb="Ready-to-post, grounded briefs for Nubra's retail audience across all platforms, topped up hourly. Post the copy where it points, then mark it Acted so the queue stays honest."
      />
      <TimeFilter current={w} allowAll="All briefs" />
      {/* Suspense: the queue reads useSearchParams (window/from_ts/to_ts) */}
      <Suspense>
        <ContentQueue base="/content-queue" />
      </Suspense>
      <ProposalArchive />
    </div>
  );
}
