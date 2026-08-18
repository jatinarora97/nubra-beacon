import { PageHeader } from "@/components/ui";
import { ApiKeysManager } from "./api-keys-manager";

export const dynamic = "force-dynamic";

export default function ApiAccessPage() {
  return (
    <div>
      <PageHeader
        title="API access"
        blurb="The read-only Beacon API at /api/beacon/v1 lets other teams and agents pull what Beacon knows. Each consumer gets its own key; every request carries it in the X-API-Key header and is limited to 60 requests per minute per key. Keys can be revoked here at any time."
        accent="bg-muted"
      />
      <ApiKeysManager />
    </div>
  );
}
