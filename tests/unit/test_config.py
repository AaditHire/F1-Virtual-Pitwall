import pytest

from f1_pitwall.config import Settings


def test_cors_origins_accept_comma_separated_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PITWALL_CORS_ORIGINS",
        "http://localhost:3000, http://127.0.0.1:3000",
    )
    settings = Settings()
    assert settings.cors_origins == (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )
