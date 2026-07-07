import Link from "next/link";
import { PageHeader, SectionCard } from "@/components/ui";

const STAGES: { name: string; tone: string; what: string }[] = [
  { name: "Listen", tone: "bg-trends", what: "Pulls posts and comments from X and Reddit communities where Indian traders talk." },
  { name: "Clean", tone: "bg-muted", what: "Links copy-paste duplicates together and sets aside spam and crypto-only chatter." },
  { name: "Understand", tone: "bg-voices", what: "AI tags every item: topic, what the person wants, how they feel, which broker they mean." },
  { name: "Roll up", tone: "bg-warn", what: "Single posts become the bigger picture: trends, broker issues, feature asks, rising voices." },
  { name: "Recommend", tone: "bg-opps", what: "Scores conversations worth joining and writes safe reply drafts for each one." },
  { name: "Compose", tone: "bg-content", what: "Packages everything into hourly heads-ups, a daily roundup, and a Saturday weekly." },
  { name: "Deliver", tone: "bg-danger", what: "Sends to Slack and email, archives everything, and powers this dashboard." },
];

const SAFETY: { name: string; what: string }[] = [
  { name: "Grounded", what: "Drafts may only claim what is in the approved USP catalog (the Grounding page). No invented features, ever." },
  { name: "Triple-checked", what: "Every draft passes three gates: automatic rule checks, an AI compliance review, and finally a human." },
  { name: "Humans post", what: "Beacon never publishes anything. It recommends; a person always makes the final call and presses send." },
];

const PAGES: { href: string; name: string; answers: string }[] = [
  { href: "/", name: "Overview", answers: "What happened today and what deserves attention right now?" },
  { href: "/trends", name: "Trends", answers: "What is the community talking about, and is it accelerating?" },
  { href: "/issues", name: "Broker issues", answers: "What are traders complaining about, per broker — including Nubra?" },
  { href: "/features", name: "Feature requests", answers: "What do traders keep asking for, across any broker?" },
  { href: "/nubra", name: "Nubra mentions", answers: "What are people saying about Nubra — the positive side?" },
  { href: "/weekly", name: "Weekly roundup", answers: "What emerged this week, and what keeps coming back?" },
  { href: "/opportunities", name: "Opportunities", answers: "Which conversations are worth joining, with drafts ready?" },
  { href: "/content", name: "Content briefs", answers: "What should the team make today, for which platform?" },
  { href: "/voices", name: "Voices", answers: "Which community members consistently matter in our niche?" },
  { href: "/explore", name: "Explore data", answers: "What raw posts sit behind every number here? (Verify anything.)" },
  { href: "/sources", name: "Sources", answers: "What does Beacon listen to? Add subreddits, hashtags, handles, keywords." },
  { href: "/grounding", name: "Grounding (USPs)", answers: "What is Beacon allowed to claim about Nubra in drafts?" },
  { href: "/requests", name: "Beacon requests", answers: "What should this dashboard do next? Log your asks." },
  { href: "/llm", name: "LLM usage", answers: "What is the AI layer costing, per run and per stage?" },
];

const NUMBERS: [string, string][] = [
  ["Volume", "distinct posts + comments on a topic in the window, duplicates merged. The bar on Trends."],
  ["Momentum (z)", "how unusual today's volume is vs the topic's own 7-day baseline. Needs a week of history."],
  ["Engagement", "real interactions: likes + replies + shares. On Trends it is shown log-scaled as an index so one viral post cannot drown the chart."],
  ["Relevance score", "the 0-100 ranking on Opportunities: 30% relevance to Nubra + 25% freshness + 15% reach + 15% opportunity type + 15% author quality."],
];

const HUMANS_OWN: string[] = [
  "Acting on opportunities — copying a draft, posting it (or not), and marking the card acted or dismissed.",
  "Editing content briefs — directly or by telling Beacon what to change; every revision is re-checked for compliance.",
  "Publishing the grounding catalog — each save is a new version the next draft run picks up.",
  "Activating suggestions — emerging themes on Trends and discovered hashtags on Sources collect data only after a human turns them on.",
  "Managing sources — everything Beacon listens to is added, paused, or removed on the Sources page.",
];

const FAQ: [string, string][] = [
  ["Why does X data look stale?",
   "Live X collection is paid (twitterapi.io) and the credits are currently exhausted, so X shows the last collected data plus a CSV backfill. Reddit is fully live. The topbar states the current mode."],
  ["Why do some pages show 'nothing yet'?",
   "Quality bars are deliberate: a trend needs 3+ items, a feature theme needs 2+ merged mentions, and momentum needs 7 days of history. Empty states mean the bar was not crossed — not that the system is broken. A red banner appears if the backend is actually down."],
  ["What does 'assumed-v0 grounding' mean?",
   "The USP catalog drafts are grounded on is engineering's best-guess seed. Marketing's vetted catalog replaces it as a new version on the Grounding page — until then, treat product claims in drafts with extra care."],
  ["Does Beacon ever post on its own?",
   "No. Nothing is ever published automatically. Beacon recommends and drafts; humans review, edit, and post."],
];

export default function HowItWorksPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="How Beacon works"
        accent="bg-trends"
        blurb="The whole system in plain English: what Beacon listens to, how raw posts become recommendations, and where humans stay in charge. No code knowledge needed."
      />

      <SectionCard>
        <div className="micro mb-4">The pipeline — every hour, in seven steps</div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4 lg:grid-cols-7">
          {STAGES.map((s, i) => (
            <div key={s.name} className="rounded-[10px] border border-line bg-surface2/50 p-3">
              <span className={`mb-2 block h-1 w-8 rounded-full ${s.tone}`} />
              <div className="flex items-baseline gap-1.5">
                <span className="text-[11px] font-semibold tabular-nums text-muted">{i + 1}</span>
                <span className="text-[13px] font-semibold">{s.name}</span>
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{s.what}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12px] text-muted">
          Runs hourly 08:00-20:00 IST for heads-ups, with a deeper build at 06:00 and a
          Saturday 10:00 weekly. Steps 1-4 measure the world; steps 5-7 turn it into work
          the team can act on.
        </p>
      </SectionCard>

      <SectionCard>
        <div className="micro mb-4">The safety story — why drafts can be trusted</div>
        <div className="grid gap-2 md:grid-cols-3">
          {SAFETY.map((s, i) => (
            <div key={s.name} className="rounded-[10px] border border-line bg-surface2/50 p-3">
              <div className="flex items-baseline gap-1.5">
                <span className="text-[11px] font-semibold tabular-nums text-muted">{i + 1}</span>
                <span className="text-[13px] font-semibold">{s.name}</span>
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{s.what}</p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[12px] text-muted">
          Nubra is a SEBI-regulated broker — every check exists so nothing leaves this
          system that compliance would not sign. Every gate decision is logged to an audit
          trail.
        </p>
      </SectionCard>

      <SectionCard>
        <div className="micro mb-3">What each page answers</div>
        <div className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2">
          {PAGES.map((p) => (
            <div key={p.href} className="text-[12.5px] leading-relaxed">
              <Link href={p.href} className="font-medium text-ink hover:underline">
                {p.name}
              </Link>{" "}
              <span className="text-muted">— {p.answers}</span>
            </div>
          ))}
        </div>
      </SectionCard>

      <SectionCard>
        <div className="micro mb-3">Where the numbers come from</div>
        <div className="space-y-1.5">
          {NUMBERS.map(([term, def]) => (
            <p key={term} className="text-[12.5px] leading-relaxed">
              <span className="font-medium text-ink">{term}</span>{" "}
              <span className="text-muted">— {def}</span>
            </p>
          ))}
        </div>
      </SectionCard>

      <SectionCard>
        <div className="micro mb-3">What humans own (Beacon never does these)</div>
        <ul className="space-y-1.5">
          {HUMANS_OWN.map((h) => (
            <li key={h} className="flex gap-2 text-[12.5px] leading-relaxed text-muted">
              <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-opps" />
              <span>{h}</span>
            </li>
          ))}
        </ul>
      </SectionCard>

      <SectionCard>
        <div className="micro mb-3">Honest FAQ</div>
        <div className="space-y-3">
          {FAQ.map(([q, a]) => (
            <div key={q}>
              <p className="text-[13px] font-medium">{q}</p>
              <p className="mt-0.5 text-[12.5px] leading-relaxed text-muted">{a}</p>
            </div>
          ))}
        </div>
      </SectionCard>

      <p className="text-[11.5px] text-muted">
        For engineers and PMs: the full API reference lives in the repo at
        docs/api-reference-2026-07-07.md.
      </p>
    </div>
  );
}
