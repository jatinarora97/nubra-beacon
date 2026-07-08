-- Persist the rendered roundup message (user request 2026-07-08): the DB row
-- should carry the exact markdown that was archived/sent, like headsups does.
ALTER TABLE roundups ADD COLUMN markdown text;
