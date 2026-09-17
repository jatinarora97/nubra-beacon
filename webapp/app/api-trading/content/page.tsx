import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { ContentQueue } from "@/components/content-queue";
import { pickWindow } from "@/lib/window";

export default async function ApiTradingContentPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  // defaultAll: the queue opens on every brief; chips narrow by created_at.
  const w = pickWindow(await searchParams, true);
  return (
    <div>
      <PageHeader
        title="API-trading content queue"
        accent="bg-content"
        blurb="Ready-to-post briefs for the API/algo audience, topped up hourly and grounded in real community threads. Post the copy where it points, then mark it Acted so the queue stays honest."
      />
      <TimeFilter current={w} allowAll="All briefs" />
      {/* Suspense: the queue reads useSearchParams (window/from_ts/to_ts) */}
      <Suspense>
        <ContentQueue base="/api-trading/content" />
      </Suspense>
    </div>
  );
}
