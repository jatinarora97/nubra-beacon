-- SSO authorization (docs/sso-decisions-2026-08-19.md): Google authenticates,
-- this table authorizes. Approvals flip rows instantly — no restarts.

CREATE TABLE sso_allowlist (
    email          text        PRIMARY KEY,
    status         text        NOT NULL DEFAULT 'pending'
                               CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_at   timestamptz NOT NULL DEFAULT now(),
    last_pinged_at timestamptz,          -- Slack-notification dedup (24h)
    decided_by     text,
    decided_at     timestamptz
);

INSERT INTO sso_allowlist (email, status, decided_by, decided_at) VALUES
    ('jatinarora@zanskar.xyz',       'approved', 'seed', now()),
    ('anuragsrivastava@zanskar.xyz', 'approved', 'seed', now()),
    ('vandana@zanskar.xyz',          'approved', 'seed', now()),
    ('dhanush@zanskar.xyz',          'approved', 'seed', now()),
    ('subothsundar@zanskar.xyz',     'approved', 'seed', now()),
    ('deepender@zanskarsec.com',     'approved', 'seed', now());
