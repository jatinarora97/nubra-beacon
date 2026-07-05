-- Free the content-proposal format (user decision 2026-07-05): the LLM proposes the
-- creative treatment freely; control lives in a registry-configured taxonomy
-- (format_family + platform) validated at the app layer, not a DB CHECK.

ALTER TABLE content_proposals DROP CONSTRAINT IF EXISTS content_proposals_format_check;
ALTER TABLE content_proposals ADD COLUMN IF NOT EXISTS format_family text;
ALTER TABLE content_proposals ADD COLUMN IF NOT EXISTS platform text;
UPDATE content_proposals SET format_family = format WHERE format_family IS NULL;
