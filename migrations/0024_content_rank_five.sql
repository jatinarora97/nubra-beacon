-- Daily content briefs: 3 -> 5. The original column CHECK only allowed ranks 1..3, which would reject the
-- 4th and 5th brief and fail the whole insert. Drop whatever CHECK constrains `rank` (found by definition,
-- not by name, so an auto-generated name cannot leave the old rule behind) and replace it with 1..5.
-- Existing rows (ranks 1..3) are valid under the new rule.
DO $$
DECLARE c text;
BEGIN
    FOR c IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'content_proposals'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) ILIKE '%rank%'
    LOOP
        EXECUTE format('ALTER TABLE content_proposals DROP CONSTRAINT %I', c);
    END LOOP;
END $$;

ALTER TABLE content_proposals
    ADD CONSTRAINT content_proposals_rank_check CHECK (rank BETWEEN 1 AND 5);
