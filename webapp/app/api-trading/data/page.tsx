import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { TimeFilter } from "@/components/time-filter";
import { pickLensWindow } from "../lens";
import { LensDataTable } from "./lens-data-table";

export default async function ApiTradingDataPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const w = pickLensWindow(await searchParams);
  return (
    <div>
      <PageHeader
        title="API-trading data"
        accent="bg-voices"
        blurb="Every item the API-trader lens classified, with its raw text and lens read. Theme chips on the Overview deep-link here prefiltered."
      />
      <TimeFilter current={w} />
      {/* Suspense: the table reads useSearchParams (?theme= deep-links + window) */}
      <Suspense>
        <LensDataTable />
      </Suspense>
    </div>
  );
}
