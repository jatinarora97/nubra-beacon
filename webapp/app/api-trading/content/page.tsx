import { PageHeader } from "@/components/ui";
import { ContentQueue } from "./content-queue";

export default function ApiTradingContentPage() {
  return (
    <div>
      <PageHeader
        title="API-trading content queue"
        accent="bg-content"
        blurb="Ready-to-post briefs for the API/algo audience, topped up hourly and grounded in real community threads. Post the copy where it points, then mark it Acted so the queue stays honest."
      />
      <ContentQueue />
    </div>
  );
}
