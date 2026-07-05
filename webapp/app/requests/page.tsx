import { PageHeader } from "@/components/ui";
import { RequestIntake } from "./request-intake";

export const dynamic = "force-dynamic";

export default function RequestsPage() {
  return (
    <div>
      <PageHeader
        title="Beacon requests"
        blurb="What should this dashboard do next? Log the sections, views and capabilities you want — every entry lands in the feedback table and shapes the build backlog. Feature asks from traders about Nubra itself live under Feature requests; this page is about Beacon."
        accent="bg-content"
      />
      <RequestIntake />
    </div>
  );
}
