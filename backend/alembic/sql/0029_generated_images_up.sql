-- 0029: the Quick answer mode, and generated illustrations (services/images.py). Made only for signed-in users who ask for
-- a picture, when an image provider is configured (off by default); never statistics. Image
-- calls are metered like the other providers (provider_call capability 'image').

-- Quick answers (a fast internet answer) are stored with their mode like the others.
ALTER TABLE assistant_message DROP CONSTRAINT ck_assistant_message_mode;
ALTER TABLE assistant_message ADD CONSTRAINT ck_assistant_message_mode
    CHECK (mode IS NULL OR mode IN ('quick', 'ask', 'analyze', 'research', 'compare', 'scenario'));

CREATE TABLE generated_image (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
    prompt      text NOT NULL CHECK (length(prompt) BETWEEN 1 AND 4000),
    purpose     text NOT NULL CHECK (purpose IN ('illustration', 'infographic', 'concept', 'diagram_art')),
    provider    text NOT NULL,
    model       text NOT NULL,
    mime        text NOT NULL CHECK (mime IN ('image/png', 'image/jpeg', 'image/webp')),
    data        bytea NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX generated_image_user_created ON generated_image (user_id, created_at DESC);

ALTER TABLE provider_call DROP CONSTRAINT provider_call_capability_check;
ALTER TABLE provider_call ADD CONSTRAINT provider_call_capability_check CHECK (
    capability IN (
        'answer', 'search', 'retrieve', 'image',
        'test_answer', 'test_search', 'test_retrieve', 'test_image'
    )
);
