"""Tests for GitHub Copilot provider functionality."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.providers.github_copilot_auth import (
    GitHubDeviceFlowError,
    request_device_code,
)
from nanobot.providers.github_copilot_token import (
    CopilotTokenError,
    _is_token_valid,
    _load_cached_token,
    _save_token_cache,
)


@pytest.mark.asyncio
async def test_request_device_code_success():
    """Test successful device code request."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "device_code": "test_device_code",
        "user_code": "ABCD-1234",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        result = await request_device_code()

        assert result["device_code"] == "test_device_code"
        assert result["user_code"] == "ABCD-1234"
        assert result["verification_uri"] == "https://github.com/login/device"


@pytest.mark.asyncio
async def test_request_device_code_missing_fields():
    """Test device code request with missing fields."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "device_code": "test_device_code",
        # Missing required fields
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        with pytest.raises(GitHubDeviceFlowError, match="Missing required fields"):
            await request_device_code()


def test_is_token_valid_expired():
    """Test token validation with expired token."""
    now_ms = int(time.time() * 1000)
    expired_token = {
        "token": "test_token",
        "expiresAt": now_ms - 1000,  # Expired 1 second ago
        "updatedAt": now_ms - 10000,
    }

    assert not _is_token_valid(expired_token)


def test_is_token_valid_expiring_soon():
    """Test token validation with token expiring soon."""
    now_ms = int(time.time() * 1000)
    expiring_token = {
        "token": "test_token",
        "expiresAt": now_ms + 60000,  # Expires in 1 minute (within 5 min margin)
        "updatedAt": now_ms - 10000,
    }

    assert not _is_token_valid(expiring_token)


def test_is_token_valid_valid():
    """Test token validation with valid token."""
    now_ms = int(time.time() * 1000)
    valid_token = {
        "token": "test_token",
        "expiresAt": now_ms + 600000,  # Expires in 10 minutes
        "updatedAt": now_ms - 10000,
    }

    assert _is_token_valid(valid_token)


def test_save_and_load_token_cache(tmp_path):
    """Test saving and loading token cache."""
    # Set up temporary cache path
    cache_path = tmp_path / "test_cache.json"

    with patch(
        "nanobot.providers.github_copilot_token.TOKEN_CACHE_PATH", cache_path
    ):
        # Save token
        now_ms = int(time.time() * 1000)
        expires_at_ms = now_ms + 1800000  # 30 minutes

        _save_token_cache("test_token_123", expires_at_ms)

        # Verify file was created
        assert cache_path.exists()

        # Load token
        loaded = _load_cached_token()

        assert loaded is not None
        assert loaded["token"] == "test_token_123"
        assert loaded["expiresAt"] == expires_at_ms
        assert "updatedAt" in loaded


def test_load_cached_token_not_found():
    """Test loading token when cache doesn't exist."""
    with patch(
        "nanobot.providers.github_copilot_token.TOKEN_CACHE_PATH",
        Path("/nonexistent/path.json"),
    ):
        result = _load_cached_token()
        assert result is None


def test_load_cached_token_invalid_json(tmp_path):
    """Test loading token with invalid JSON."""
    cache_path = tmp_path / "invalid_cache.json"
    cache_path.write_text("invalid json{}")

    with patch(
        "nanobot.providers.github_copilot_token.TOKEN_CACHE_PATH", cache_path
    ):
        result = _load_cached_token()
        assert result is None


def test_load_cached_token_missing_fields(tmp_path):
    """Test loading token with missing required fields."""
    cache_path = tmp_path / "incomplete_cache.json"
    cache_path.write_text(json.dumps({"token": "test"}))  # Missing expiresAt

    with patch(
        "nanobot.providers.github_copilot_token.TOKEN_CACHE_PATH", cache_path
    ):
        result = _load_cached_token()
        assert result is None
