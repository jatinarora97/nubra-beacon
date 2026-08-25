import { Suspense } from "react";
import { PageHeader } from "@/components/ui";
import { LensDataTable } from "./lens-data-table";

export default function ApiTradingDataPage() {
  return (
    <div>
      <PageHeader
        title="API-trading data"
        accent="bg-voices"
        blurb="Every item the API-trader lens classified, with its raw text and lens read. Theme chips on the Overview deep-link here prefiltered."
      />
      {/* Suspense: the table reads useSearchParams (?theme= deep-links etc.) */}
      <Suspense>
        <LensDataTable />
      </Suspense>
    </div>
  );
}
