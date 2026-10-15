"""The test suite never sees a developer's provider keys (backend/.env or the shell), so no
automated test can call a real model, search, speech, mail or SMS service."""

from __future__ import annotations

import os


def test_tests_ignore_env_file_and_shell_credentials() -> None:
    from app.core.config import Settings

    assert os.environ.get("OSRIP_ENV_FILE") == "none"
    assert Settings.model_config["env_file"] is None
    settings = Settings()
    assert settings.anthropic_api_key is None
    assert settings.research_api_key is None
    assert not [
        n
        for n in os.environ
        if n.endswith(("_API_KEY", "_SPEECH_KEY", "_PASSWORD")) and n.startswith("OSRIP_")
    ]
