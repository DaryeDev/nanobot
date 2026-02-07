"""GitHub OAuth device flow authentication for Copilot."""

import asyncio
import time
from typing import Literal

import httpx
from loguru import logger


# OAuth client configuration (same as OpenClaw)
GITHUB_OAUTH_CLIENT_ID = "Iv1.b507a08c87ecfe98"
GITHUB_OAUTH_SCOPE = "read:user"

# GitHub OAuth endpoints
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubDeviceFlowError(Exception):
    """Raised when GitHub device flow fails."""
    pass


async def request_device_code() -> dict[str, str | int]:
    """
    Request a device code from GitHub.
    
    Returns:
        dict with keys: device_code, user_code, verification_uri, expires_in, interval
    
    Raises:
        GitHubDeviceFlowError: If the request fails.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                GITHUB_DEVICE_CODE_URL,
                data={
                    "client_id": GITHUB_OAUTH_CLIENT_ID,
                    "scope": GITHUB_OAUTH_SCOPE,
                },
                headers={"Accept": "application/json"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            
            # Validate response contains required fields
            required_fields = ["device_code", "user_code", "verification_uri", "expires_in", "interval"]
            if not all(field in data for field in required_fields):
                raise GitHubDeviceFlowError(f"Missing required fields in response: {data}")
            
            logger.debug(f"Device code requested: {data.get('user_code')}")
            return data
        except httpx.HTTPError as e:
            raise GitHubDeviceFlowError(f"Failed to request device code: {e}") from e


async def poll_for_token(
    device_code: str,
    interval: int = 5,
    expires_in: int = 900,
) -> str:
    """
    Poll GitHub for access token.
    
    Args:
        device_code: The device code from request_device_code()
        interval: Polling interval in seconds (from GitHub response)
        expires_in: Expiration time in seconds (from GitHub response)
    
    Returns:
        GitHub access token
    
    Raises:
        GitHubDeviceFlowError: If authorization fails or expires.
    """
    start_time = time.time()
    poll_interval = interval
    
    async with httpx.AsyncClient() as client:
        while time.time() - start_time < expires_in:
            await asyncio.sleep(poll_interval)
            
            try:
                response = await client.post(
                    GITHUB_ACCESS_TOKEN_URL,
                    data={
                        "client_id": GITHUB_OAUTH_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                    timeout=30.0,
                )
                
                data = response.json()
                error = data.get("error")
                
                if not error:
                    # Success! We got the access token
                    access_token = data.get("access_token")
                    if not access_token:
                        raise GitHubDeviceFlowError(f"No access_token in response: {data}")
                    logger.info("Successfully obtained GitHub access token")
                    return access_token
                
                # Handle specific error codes
                if error == "authorization_pending":
                    # User hasn't authorized yet, keep polling
                    logger.debug("Authorization pending, continuing to poll...")
                    continue
                elif error == "slow_down":
                    # We're polling too fast, increase interval
                    poll_interval += 5
                    logger.debug(f"Slowing down polling interval to {poll_interval}s")
                    continue
                elif error == "expired_token":
                    raise GitHubDeviceFlowError("Device code expired. Please try again.")
                elif error == "access_denied":
                    raise GitHubDeviceFlowError("Access denied by user.")
                else:
                    # Unknown error
                    raise GitHubDeviceFlowError(f"Unexpected error: {error} - {data.get('error_description', '')}")
                    
            except httpx.HTTPError as e:
                logger.warning(f"HTTP error during polling: {e}")
                # Continue polling unless we've expired
                if time.time() - start_time >= expires_in:
                    raise GitHubDeviceFlowError(f"Polling failed: {e}") from e
                continue
    
    raise GitHubDeviceFlowError("Device code expired before authorization completed.")


async def authenticate() -> str:
    """
    Complete GitHub device flow authentication.
    
    Returns:
        GitHub access token
    
    Raises:
        GitHubDeviceFlowError: If authentication fails.
    """
    # Request device code
    device_flow = await request_device_code()
    
    # Poll for token
    token = await poll_for_token(
        device_code=device_flow["device_code"],
        interval=device_flow["interval"],
        expires_in=device_flow["expires_in"],
    )
    
    return token
