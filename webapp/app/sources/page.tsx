import { PageHeader } from "@/components/ui";
import { SourcesManager } from "./sources-manager";

export const dynamic = "force-dynamic";

export default function SourcesPage() {
  return (
    <div>
      <PageHeader
        title="Collection sources"
        blurb="What Beacon listens to. Changes apply automatically on the next hourly scrape run — no code, no deploy. Subreddits are fetched across the new / hot / rising feeds (top once daily); X hashtags, handles, queries and keywords feed the X search collector (budget-capped). Keywords with the Reddit lens act as a filter over what the subreddits already bring in — no extra fetches."
        accent="bg-muted"
      />
      <SourcesManager />
    </div>
  );
}
