"""GitHub Copilot token management and caching.

This module handles:
- Exchanging GitHub tokens for Copilot API tokens
- Caching tokens with expiration tracking
- Auto-refresh with 5-minute safety buffer
- Base URL extraction from token metadata
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from loguru import logger


@dataclass
class CachedCopilotToken:
    """Cached Copilot token with expiration."""
    token: str
    expires_at: int  # Unix timestamp in seconds
    base_url: str
    source: str = "cache"


def get_cache_path() -> Path:
    """Get the Copilot token cache file path."""
    cache_dir = Path.home() / ".nanobot" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "copilot_token.json"


def load_cached_token() -> CachedCopilotToken | None:
    """Load cached token from disk if it exists and is valid."""
    cache_path = get_cache_path()
    if not cache_path.exists():
        return None

    try:
        with open(cache_path) as f:
            data = json.load(f)

        # Validate required fields
        if not all(k in data for k in ("token", "expires_at", "base_url")):
            return None

        return CachedCopilotToken(
            token=data["token"],
            expires_at=data["expires_at"],
            base_url=data["base_url"],
            source="cache"
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_cached_token(token_data: CachedCopilotToken) -> None:
    """Save token to cache."""
    cache_path = get_cache_path()
    data = {
        "token": token_data.token,
        "expires_at": token_data.expires_at,
        "base_url": token_data.base_url,
    }
    with open(cache_path, "w") as f:
        json.dump(data, f, indent=2)


def is_token_valid(token_data: CachedCopilotToken, buffer_seconds: int = 300) -> bool:
    """Check if token is still valid with a safety buffer (default 5 minutes)."""
    now = int(time.time())
    return token_data.expires_at > (now + buffer_seconds)


def derive_copilot_api_base_url(token: str) -> str:
    """
    Extract base URL from Copilot token metadata.

    Copilot tokens contain metadata in format: "token;proxy-ep=proxy.example.com;"
    Converts: proxy.example.com → https://api.example.com

    Args:
        token: Copilot API token with embedded metadata

    Returns:
        Base URL string (defaults to individual Copilot endpoint)
    """
    default_url = "https://api.individual.githubcopilot.com"

    if ";" not in token:
        return default_url

    try:
        # Parse metadata from token
        parts = token.split(";")
        for part in parts:
            if "proxy-ep=" in part:
                proxy_host = part.split("proxy-ep=")[-1].strip()
                if proxy_host:
                    # Convert proxy.example.com → api.example.com
                    api_host = proxy_host.replace("proxy.", "api.", 1)
                    return f"https://{api_host}"
    except Exception as e:
        logger.debug(f"Failed to parse token metadata: {e}")

    return default_url


async def exchange_github_token_for_copilot(github_token: str) -> dict[str, Any]:
    """
    Exchange a GitHub token for a Copilot API token.

    Args:
        github_token: GitHub OAuth or personal access token

    Returns:
        Dict with keys: token, expires_at, base_url

    Raises:
        httpx.HTTPStatusError: If the request fails
    """
    url = "https://api.github.com/copilot_internal/v2/token"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

    # Parse response
    token = data.get("token", "")
    expires_at = data.get("expires_at", 0)

    # Derive base URL from token
    base_url = derive_copilot_api_base_url(token)

    return {
        "token": token,
        "expires_at": expires_at,
        "base_url": base_url,
    }


async def resolve_copilot_api_token(github_token: str) -> dict[str, Any]:
    """
    Resolve a Copilot API token, using cache if valid or refreshing if needed.

    This is the main entry point for getting a Copilot token. It:
    1. Checks if there's a valid cached token (with 5-minute buffer)
    2. If not, exchanges the GitHub token for a new Copilot token
    3. Saves the new token to cache
    4. Returns token data

    Args:
        github_token: GitHub OAuth or personal access token

    Returns:
        Dict with keys: token (str), expires_at (int), source (str), base_url (str)

    Raises:
        httpx.HTTPStatusError: If token exchange fails
    """
    # Try to use cached token
    cached = load_cached_token()
    if cached and is_token_valid(cached):
        logger.debug("Using cached Copilot token")
        return {
            "token": cached.token,
            "expires_at": cached.expires_at,
            "source": "cache",
            "base_url": cached.base_url,
        }

    # Cache miss or expired - get fresh token
    logger.debug("Refreshing Copilot token from GitHub")
    token_data = await exchange_github_token_for_copilot(github_token)

    # Save to cache
    cached_token = CachedCopilotToken(
        token=token_data["token"],
        expires_at=token_data["expires_at"],
        base_url=token_data["base_url"],
        source="fresh"
    )
    save_cached_token(cached_token)

    return {
        "token": token_data["token"],
        "expires_at": token_data["expires_at"],
        "source": "fresh",
        "base_url": token_data["base_url"],
    }
