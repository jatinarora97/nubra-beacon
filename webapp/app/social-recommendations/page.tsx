import { get } from "@/lib/api";
import type {
  SocialRecommendation,
  SocialRecommendationPreview,
  SocialRecommendationStatus,
} from "@/lib/types";
import { PageHeader } from "@/components/ui";
import { RecommendationWorkspace } from "./recommendation-workspace";

export const dynamic = "force-dynamic";

export default async function SocialRecommendationsPage() {
  const [recommendations, status, preview] = await Promise.all([
    get<SocialRecommendation[]>("/social-recommendations", []),
    get<SocialRecommendationStatus>("/social-recommendations/status", {
      module: "social_recommendations",
      ready: false,
    }),
    get<SocialRecommendationPreview>("/social-recommendations/preview?days=30", {}),
  ]);

  return (
    <div>
      <PageHeader
        title="Social recommendations"
        accent="bg-content"
        blurb="Ready-to-publish social copy grounded in current community evidence and Nubra’s verified product context. Retail and API ideas stay separate. Exact copy comes first; open the supporting details to see the evidence, feature mapping, timing and visual direction."
      />
      <RecommendationWorkspace
        initial={recommendations}
        moduleStatus={status}
        preview={preview}
      />
    </div>
  );
}
