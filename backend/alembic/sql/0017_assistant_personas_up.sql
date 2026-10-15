-- 0017: two selectable assistant personas (Al Mulhim and Ilham) in profile version 3.
-- assistant_persona: the persona a signed-in person chose (NULL = the profile's default).
-- assistant_message.persona: the persona that gave an assistant reply, so a conversation that
-- switched persona keeps showing who said what. Personas share knowledge, tools, permissions,
-- sources, history and the guest allowance; only the name, introduction, portrait and voice
-- differ. Profile version 3 is published by the migration script.

ALTER TABLE app_user
    ADD COLUMN assistant_persona text
        CONSTRAINT ck_app_user_assistant_persona CHECK (assistant_persona ~ '^[a-z][a-z0-9_]{0,31}$');

ALTER TABLE assistant_message
    ADD COLUMN persona text
        CONSTRAINT ck_assistant_message_persona CHECK (
            persona IS NULL OR (role = 'assistant' AND persona ~ '^[a-z][a-z0-9_]{0,31}$')
        );
