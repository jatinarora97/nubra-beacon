import { PageHeader } from "@/components/ui";
import { GroundingEditor } from "./grounding-editor";

export const dynamic = "force-dynamic";

export default function GroundingPage() {
  return (
    <div>
      <PageHeader
        title="Grounding (USPs)"
        accent="bg-warn"
        blurb="The single source of truth for what Beacon is allowed to claim about Nubra. Every brand reply, rep reply and content brief grounds on this list — drafts cite these features, invented claims fail compliance. Edits publish as a new version that the next draft run picks up automatically."
      />
      <GroundingEditor />
    </div>
  );
}
