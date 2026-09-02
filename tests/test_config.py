from pathlib import Path

from src.config import PROJECT_ROOT, Settings

# The bug this file guards (measured 2026-07-17): model_config used
# env_file=".env", a RELATIVE path, which pydantic resolves against the process
# CWD. A diagnostic run from a scratch directory therefore missed the project's
# .env, silently fell back to the nomic embedding default (768-dim) against a
# bge-m3 store (1024-dim), and reported every retrieval as empty - which read
# like a corpus finding rather than a config bug.
DECOY_EMBEDDING_MODEL = "decoy-embedding-model-from-the-wrong-directory"


def test_cwd_env_file_does_not_hijack_settings(tmp_path, monkeypatch):
    """A .env sitting in the CWD must not configure the app.

    Deliberately inverted: it asserts the decoy is IGNORED rather than asserting
    the real .env is read. The real .env is gitignored and absent in CI, so a
    test that read it would pass locally and fail there.
    """
    (tmp_path / ".env").write_text(
        f"EMBEDDING_MODEL={DECOY_EMBEDDING_MODEL}\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    # A real env var would legitimately win over .env; drop it so this test
    # measures the file-resolution behaviour and nothing else.
    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)

    assert Settings().embedding_model != DECOY_EMBEDDING_MODEL


def test_env_file_is_anchored_to_the_project_root():
    """The configured env_file must be the project's own .env, by absolute path."""
    env_file = Path(Settings.model_config["env_file"])

    assert env_file.is_absolute()
    assert env_file == PROJECT_ROOT / ".env"


def test_chat_provider_defaults_to_local():
    """Asserted on the FIELD DEFAULT, not on an instance: the maintainer's real
    .env may well select openrouter, and a test that read it would pass in CI and
    fail locally (or the reverse). Same reasoning as the decoy test above."""
    assert Settings.model_fields["chat_provider"].default == "local"


def test_openrouter_without_a_key_is_rejected():
    """Fail loud on incomplete config - same rule as the embedding-model guard: a
    misconfiguration must never silently serve garbage (here: 401s at request time
    instead of one clear error at startup)."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(chat_provider="openrouter",
                 openrouter_api_key="",
                 openrouter_model="vendor/model-x")


def test_openrouter_without_a_model_is_rejected():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(chat_provider="openrouter",
                 openrouter_api_key="key",
                 openrouter_model="")


def test_openrouter_with_key_and_model_is_accepted():
    s = Settings(chat_provider="openrouter",
                 openrouter_api_key="key",
                 openrouter_model="vendor/model-x")
    assert s.openrouter_model == "vendor/model-x"


def test_local_provider_does_not_require_openrouter_fields():
    """The default path must not be collateral damage of the new validation."""
    s = Settings(chat_provider="local", openrouter_api_key="", openrouter_model="")
    assert s.chat_provider == "local"


def test_embedding_identity_defaults_to_bge_m3():
    """Asserted on the FIELD DEFAULT (same reasoning as the chat_provider test):
    the real .env is gitignored, so an instance-level assert would be env-dependent."""
    assert Settings.model_fields["embedding_identity"].default == "bge-m3"


def test_the_rate_limit_defaults_to_sixty_a_minute():
    """THE ONE REGRESSION THE TEST SUITE CANNOT OTHERWISE SEE. tests/conftest.py
    resets the limiter between tests, so a default of 1 would ship a ceiling
    that refuses a live demo with every test still green - measured: setting
    this default to 1 leaves all 1049 passing.

    Asserted on the FIELD DEFAULT rather than an instance, for the same reason
    as the chat_provider test above: the real .env is gitignored, so an
    instance-level assert would be environment-dependent."""
    assert Settings.model_fields["rate_limit_per_minute"].default == 60


def test_embedding_endpoint_falls_back_to_lm_studio_when_unset():
    s = Settings(embedding_base_url="", embedding_api_key="")
    assert s.effective_embedding_base_url == s.lm_studio_base_url
    assert s.effective_embedding_api_key == s.lm_studio_api_key


def test_embedding_endpoint_override_wins():
    s = Settings(embedding_base_url="https://hosted.example/v1",
                 embedding_api_key="secret-key")
    assert s.effective_embedding_base_url == "https://hosted.example/v1"
    assert s.effective_embedding_api_key == "secret-key"
