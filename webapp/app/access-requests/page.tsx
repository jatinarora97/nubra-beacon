import { PageHeader } from "@/components/ui";
import { AccessRequestsManager } from "./access-requests-manager";

export const dynamic = "force-dynamic";

export default function AccessRequestsPage() {
  return (
    <div>
      <PageHeader
        title="Access requests"
        blurb="Everyone who signs in through Google SSO lands here for approval. Approvals take effect on the person's next page load. Newly approved people must also be added as test users in the Google Cloud console, since the OAuth app is still in Testing mode."
        accent="bg-muted"
      />
      <AccessRequestsManager />
    </div>
  );
}
