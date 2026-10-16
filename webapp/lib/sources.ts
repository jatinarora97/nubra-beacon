/** Sources that produce opportunities, in the order the Opportunities filter lists them. */
export const SOURCE_LABELS: Record<string, string> = {
  twitter: "X / Twitter",
  reddit: "Reddit",
  instagram: "Instagram",
  youtube: "YouTube",
  community_forum: "Forums",
  linkedin: "LinkedIn",
  github: "GitHub",
  app_review: "App reviews",
};

export const SOURCE_FILTERS = Object.entries(SOURCE_LABELS).map(([key, label]) => ({
  key,
  label,
}));

/** Display name for a source key; unknown keys are shown as they are. */
export function sourceLabel(source?: string | null): string {
  return source ? (SOURCE_LABELS[source] ?? source) : "";
}
