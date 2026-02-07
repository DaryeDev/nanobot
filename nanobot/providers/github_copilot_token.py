"""GitHub Copilot token exchange and caching."""

import json
import time
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger


# GitHub Copilot API endpoint
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"

# Default base URL for GitHub Copilot API
DEFAULT_COPILOT_BASE_URL = "https://api.individual.githubcopilot.com"

# Token cache path
TOKEN_CACHE_PATH = Path.home() / ".nanobot" / "credentials" / "github-copilot.token.json"

# Safety margin for token expiration (5 minutes in milliseconds)
EXPIRY_MARGIN_MS = 5 * 60 * 1000


class CopilotTokenError(Exception):
    """Raised when Copilot token operations fail."""
    pass


def _ensure_cache_dir():
    """Ensure the cache directory exists."""
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_cached_token() -> Optional[dict]:
    """
    Load cached Copilot token from disk.
    
    Returns:
        Cached token data or None if not found/invalid.
    """
    if not TOKEN_CACHE_PATH.exists():
        return None
    
    try:
        with open(TOKEN_CACHE_PATH, "r") as f:
            data = json.load(f)
        
        # Validate structure
        if not all(key in data for key in ["token", "expiresAt", "updatedAt"]):
            logger.warning("Invalid token cache structure, ignoring")
            return None
        
        return data
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load token cache: {e}")
        return None


def _save_token_cache(token: str, expires_at_ms: int):
    """
    Save Copilot token to cache.
    
    Args:
        token: The Copilot API token
        expires_at_ms: Expiration timestamp in milliseconds since epoch
    """
    _ensure_cache_dir()
    
    data = {
        "token": token,
        "expiresAt": expires_at_ms,
        "updatedAt": int(time.time() * 1000),
    }
    
    try:
        with open(TOKEN_CACHE_PATH, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug(f"Saved token cache to {TOKEN_CACHE_PATH}")
    except OSError as e:
        logger.error(f"Failed to save token cache: {e}")


def _is_token_valid(cached: dict) -> bool:
    """
    Check if a cached token is still valid.
    
    Args:
        cached: Cached token data
    
    Returns:
        True if token is valid and not expired (with margin)
    """
    now_ms = int(time.time() * 1000)
    expires_at_ms = cached.get("expiresAt", 0)
    
    # Check if expired (with safety margin)
    if expires_at_ms <= now_ms + EXPIRY_MARGIN_MS:
        logger.debug("Cached token expired or expiring soon")
        return False
    
    return True


async def exchange_token(github_token: str) -> tuple[str, str]:
    """
    Exchange GitHub token for Copilot API token.
    
    Args:
        github_token: GitHub personal access token
    
    Returns:
        Tuple of (copilot_token, base_url)
    
    Raises:
        CopilotTokenError: If token exchange fails.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                COPILOT_TOKEN_URL,
                headers={
                    "Authorization": f"token {github_token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
            
            if response.status_code == 401:
                raise CopilotTokenError(
                    "GitHub token is invalid or doesn't have Copilot access. "
                    "Please ensure you have an active GitHub Copilot subscription."
                )
            elif response.status_code == 404:
                raise CopilotTokenError(
                    "Copilot API not available. Please ensure you have an active GitHub Copilot subscription."
                )
            
            response.raise_for_status()
            data = response.json()
            
            # Extract token
            token = data.get("token")
            if not token:
                raise CopilotTokenError(f"No token in response: {data}")
            
            # Extract and convert base URL
            base_url = DEFAULT_COPILOT_BASE_URL
            proxy_ep = data.get("proxy-ep")
            if proxy_ep:
                # Convert proxy.* to api.*
                # Example: proxy.individual.githubcopilot.com -> api.individual.githubcopilot.com
                if proxy_ep.startswith("proxy."):
                    base_url = f"https://api.{proxy_ep[6:]}"
                else:
                    base_url = f"https://{proxy_ep}"
                logger.debug(f"Using base URL from proxy-ep: {base_url}")
            
            # Extract expiration time
            expires_at = data.get("expires_at")
            if expires_at:
                # expires_at is typically a Unix timestamp (seconds)
                # Convert to milliseconds
                expires_at_ms = int(expires_at * 1000) if expires_at < 10000000000 else int(expires_at)
            else:
                # Default to 30 minutes from now if not provided
                expires_at_ms = int(time.time() * 1000) + (30 * 60 * 1000)
            
            # Cache the token
            _save_token_cache(token, expires_at_ms)
            
            logger.info("Successfully exchanged GitHub token for Copilot token")
            return token, base_url
            
        except httpx.HTTPError as e:
            raise CopilotTokenError(f"Failed to exchange token: {e}") from e


async def get_copilot_token(github_token: str, force_refresh: bool = False) -> tuple[str, str]:
    """
    Get a valid Copilot API token, using cache if available.
    
    Args:
        github_token: GitHub personal access token
        force_refresh: Force refresh even if cached token is valid
    
    Returns:
        Tuple of (copilot_token, base_url)
    
    Raises:
        CopilotTokenError: If token retrieval fails.
    """
    # Try to use cached token first
    if not force_refresh:
        cached = _load_cached_token()
        if cached and _is_token_valid(cached):
            logger.debug("Using cached Copilot token")
            # We don't cache base_url, so use default
            # In practice, base_url rarely changes
            return cached["token"], DEFAULT_COPILOT_BASE_URL
    
    # Exchange for new token
    return await exchange_token(github_token)


def clear_token_cache():
    """Clear the cached Copilot token."""
    if TOKEN_CACHE_PATH.exists():
        TOKEN_CACHE_PATH.unlink()
        logger.info("Cleared token cache")
