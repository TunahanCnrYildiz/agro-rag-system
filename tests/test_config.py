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
