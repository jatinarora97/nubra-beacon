import { PageHeader } from "@/components/ui";
import { SourcesManager } from "./sources-manager";

export const dynamic = "force-dynamic";

export default function SourcesPage() {
  return (
    <div>
      <PageHeader
        title="Collection sources"
        blurb="What the radar listens to. Changes apply automatically on the next hourly scrape run — no code, no deploy. Subreddits are fetched across the new / hot / rising feeds (top once daily); X hashtags, handles and queries feed the X search collector (budget-capped)."
        accent="bg-muted"
      />
      <SourcesManager />
    </div>
  );
}
