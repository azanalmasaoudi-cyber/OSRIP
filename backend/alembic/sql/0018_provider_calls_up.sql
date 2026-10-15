-- 0018: one row per call to an external AI or search provider (answering model, search route,
-- or an administrator's readiness test). It records what happened, never what was asked:
-- no prompt, question, query, answer or personal data is stored. Used for the provider
-- readiness view (configured / tested / failed) and for the daily request and spending limits.

CREATE TABLE provider_call (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider            text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_-]{0,31}$'),
    capability          text NOT NULL CHECK (capability IN ('answer', 'search', 'test_answer', 'test_search')),
    model               text CHECK (model IS NULL OR length(model) <= 120),
    -- ok, or the failure code: timeout, network, http_401, invalid_response, budget_exhausted, ...
    status              text NOT NULL CHECK (status ~ '^[a-z0-9_]{1,40}$'),
    duration_ms         integer NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    input_tokens        integer CHECK (input_tokens >= 0),
    output_tokens       integer CHECK (output_tokens >= 0),
    searches            integer CHECK (searches >= 0),
    -- Only when prices are configured (OSRIP_PROVIDER_PRICES); never guessed.
    estimated_cost_usd  numeric(12, 6) CHECK (estimated_cost_usd >= 0),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_provider_call_recent ON provider_call (provider, created_at DESC);
