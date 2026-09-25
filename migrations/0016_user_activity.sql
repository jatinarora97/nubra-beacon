-- Team-activity tracking (expansion plan workstream 4). Fed by the SSO
-- gate's authz calls (~1/min per active user) — a "visit" increments when
-- the previous activity is >30 min old (sessions, not clicks).

CREATE TABLE user_activity (
    email      text        NOT NULL,
    day        date        NOT NULL,
    visits     int         NOT NULL DEFAULT 1,
    first_seen timestamptz NOT NULL DEFAULT now(),
    last_seen  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (email, day)
);
