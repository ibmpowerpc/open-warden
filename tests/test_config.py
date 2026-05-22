import pytest

from src.config import get_model_ids
from src.config import get_opencode_attempts


def test_get_model_ids_uses_config_and_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENCODE_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("OPENCODE_REVIEW_FALLBACK_MODELS", raising=False)

    assert get_model_ids(
        {
            "id": "primary",
            "fallback_ids": ["fallback-a", "fallback-b"],
        }
    ) == ["primary", "fallback-a", "fallback-b"]


def test_get_model_ids_prefers_env_primary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_REVIEW_MODEL", "env-primary")
    monkeypatch.delenv("OPENCODE_REVIEW_FALLBACK_MODELS", raising=False)

    assert get_model_ids({"id": "config-primary", "fallback_ids": ["fallback"]}) == [
        "env-primary",
        "fallback",
    ]


def test_get_model_ids_uses_env_fallbacks_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENCODE_REVIEW_MODEL", "primary")
    monkeypatch.setenv("OPENCODE_REVIEW_FALLBACK_MODELS", "fallback, primary, fallback")

    assert get_model_ids({"id": "config-primary"}) == ["primary", "fallback"]


def test_get_opencode_attempts_defaults_to_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_REVIEW_ATTEMPTS", raising=False)

    assert get_opencode_attempts() == 2


def test_get_opencode_attempts_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_REVIEW_ATTEMPTS", "3")

    assert get_opencode_attempts() == 3


@pytest.mark.parametrize("value", ["0", "-1", "abc"])
def test_get_opencode_attempts_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("OPENCODE_REVIEW_ATTEMPTS", value)

    with pytest.raises(SystemExit):
        get_opencode_attempts()
