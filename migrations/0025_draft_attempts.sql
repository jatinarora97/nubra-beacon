-- Remember draft attempts that produced no draft. Until now a thread the model skipped (or whose drafts failed every
-- attempt) kept brand_reply NULL and was picked again by EVERY draft run, best priority first, so a few such threads
-- could fill all max_drafted slots each hour and starve better ones (and cost Sonnet calls every time).
--   draft_attempts       runs that ended without a draft (0 = never failed)
--   draft_last_outcome   'skipped' (the model chose not to reply; never retried automatically)
--                        'dropped' (every attempt failed validation/compliance; retried a day later, up to a cap)
--   draft_attempted_at   when the last such run happened
-- Additive and defaulted: existing rows start with a clean slate. To reopen parked threads, for example after a prompt
-- change:  UPDATE opportunities SET draft_attempts=0, draft_last_outcome=NULL, draft_attempted_at=NULL
--          WHERE source='twitter' AND brand_reply IS NULL;
ALTER TABLE opportunities
    ADD COLUMN draft_attempts     smallint    NOT NULL DEFAULT 0,
    ADD COLUMN draft_last_outcome text        CHECK (draft_last_outcome IN ('skipped', 'dropped')),
    ADD COLUMN draft_attempted_at timestamptz;
