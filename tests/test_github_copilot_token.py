"""Tests for GitHub Copilot token management."""

import json
import time
from pathlib import Path

import pytest

from nanobot.providers.github_copilot_token import (
    CachedCopilotToken,
    derive_copilot_api_base_url,
    get_cache_path,
    is_token_valid,
    load_cached_token,
    save_cached_token,
)


def test_derive_copilot_api_base_url_with_proxy():
    """Test extracting base URL from token metadata."""
    token = "abc123;proxy-ep=proxy.individual.githubcopilot.com;"
    url = derive_copilot_api_base_url(token)
    assert url == "https://api.individual.githubcopilot.com"


def test_derive_copilot_api_base_url_without_proxy():
    """Test default URL when no proxy metadata."""
    token = "abc123"
    url = derive_copilot_api_base_url(token)
    assert url == "https://api.individual.githubcopilot.com"


def test_derive_copilot_api_base_url_malformed():
    """Test handling of malformed metadata."""
    token = "abc123;proxy-ep=;"
    url = derive_copilot_api_base_url(token)
    assert url == "https://api.individual.githubcopilot.com"


def test_is_token_valid_fresh():
    """Test token validity check for fresh token."""
    expires_at = int(time.time()) + 3600  # 1 hour from now
    token = CachedCopilotToken(
        token="test",
        expires_at=expires_at,
        base_url="https://api.individual.githubcopilot.com",
    )
    assert is_token_valid(token)


def test_is_token_valid_expired():
    """Test token validity check for expired token."""
    expires_at = int(time.time()) - 3600  # 1 hour ago
    token = CachedCopilotToken(
        token="test",
        expires_at=expires_at,
        base_url="https://api.individual.githubcopilot.com",
    )
    assert not is_token_valid(token)


def test_is_token_valid_within_buffer():
    """Test token validity check within safety buffer."""
    expires_at = int(time.time()) + 200  # 200 seconds from now (< 5 min buffer)
    token = CachedCopilotToken(
        token="test",
        expires_at=expires_at,
        base_url="https://api.individual.githubcopilot.com",
    )
    assert not is_token_valid(token, buffer_seconds=300)  # 5 min buffer


def test_cache_round_trip(tmp_path, monkeypatch):
    """Test saving and loading token cache."""
    # Use temp directory for cache
    cache_file = tmp_path / "copilot_token.json"
    
    def mock_get_cache_path():
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        return cache_file
    
    monkeypatch.setattr("nanobot.providers.github_copilot_token.get_cache_path", mock_get_cache_path)
    
    # Save token
    token = CachedCopilotToken(
        token="test_token_123",
        expires_at=1234567890,
        base_url="https://api.individual.githubcopilot.com",
    )
    save_cached_token(token)
    
    # Verify file exists
    assert cache_file.exists()
    
    # Load token
    loaded = load_cached_token()
    assert loaded is not None
    assert loaded.token == "test_token_123"
    assert loaded.expires_at == 1234567890
    assert loaded.base_url == "https://api.individual.githubcopilot.com"


def test_load_cached_token_missing_file(tmp_path, monkeypatch):
    """Test loading when cache file doesn't exist."""
    cache_file = tmp_path / "nonexistent" / "copilot_token.json"
    
    def mock_get_cache_path():
        return cache_file
    
    monkeypatch.setattr("nanobot.providers.github_copilot_token.get_cache_path", mock_get_cache_path)
    
    loaded = load_cached_token()
    assert loaded is None


def test_load_cached_token_invalid_json(tmp_path, monkeypatch):
    """Test loading when cache file has invalid JSON."""
    cache_file = tmp_path / "copilot_token.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("not valid json")
    
    def mock_get_cache_path():
        return cache_file
    
    monkeypatch.setattr("nanobot.providers.github_copilot_token.get_cache_path", mock_get_cache_path)
    
    loaded = load_cached_token()
    assert loaded is None


def test_load_cached_token_missing_fields(tmp_path, monkeypatch):
    """Test loading when cache file is missing required fields."""
    cache_file = tmp_path / "copilot_token.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps({"token": "abc"}))
    
    def mock_get_cache_path():
        return cache_file
    
    monkeypatch.setattr("nanobot.providers.github_copilot_token.get_cache_path", mock_get_cache_path)
    
    loaded = load_cached_token()
    assert loaded is None
