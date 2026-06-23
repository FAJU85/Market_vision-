"""Tests for Epic A3 — secret loading from environment variables."""

from __future__ import annotations

import pytest

from sqra import config


def test_get_secret_reads_hf_prefixed_var(monkeypatch):
    """Done when: secrets are read from HF_SECRET_* env vars, not hardcoded."""
    monkeypatch.setenv("HF_SECRET_MARKET_API_KEY", "token-123")
    assert config.get_secret("MARKET_API_KEY") == "token-123"


def test_get_secret_bare_fallback(monkeypatch):
    monkeypatch.delenv("HF_SECRET_MARKET_API_KEY", raising=False)
    monkeypatch.setenv("MARKET_API_KEY", "local-dev")
    assert config.get_secret("MARKET_API_KEY") == "local-dev"


def test_get_secret_missing_returns_default(monkeypatch):
    monkeypatch.delenv("HF_SECRET_NOPE", raising=False)
    monkeypatch.delenv("NOPE", raising=False)
    assert config.get_secret("NOPE", default="fallback") == "fallback"


def test_require_secret_raises_when_absent(monkeypatch):
    monkeypatch.delenv("HF_SECRET_MISSING", raising=False)
    monkeypatch.delenv("MISSING", raising=False)
    with pytest.raises(RuntimeError):
        config.require_secret("MISSING")
