"""GitHub Copilot OAuth Device Flow authentication.

This module implements GitHub's OAuth Device Flow for authenticating with Copilot:
1. Request device code from GitHub
2. Display user code to user
3. Poll for access token
4. Verify Copilot access

Reference: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow
"""

import asyncio
import time
import webbrowser
from typing import Any

import httpx
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# GitHub OAuth Client ID (same as openclaw)
CLIENT_ID = "Iv1.b507a08c87ecfe98"

console = Console()


async def request_device_code() -> dict[str, Any]:
    """
    Request a device code from GitHub OAuth.
    
    Returns:
        Dict with keys:
        - device_code: Code for polling
        - user_code: Code user enters in browser
        - verification_uri: URL where user authorizes
        - expires_in: Expiration time in seconds
        - interval: Polling interval in seconds
    
    Raises:
        httpx.HTTPStatusError: If request fails
    """
    url = "https://github.com/login/device/code"
    data = {
        "client_id": CLIENT_ID,
        "scope": "read:user",  # Minimal scope needed for Copilot
    }
    headers = {
        "Accept": "application/json",
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data, headers=headers)
        response.raise_for_status()
        return response.json()


async def poll_for_access_token(
    device_code: str,
    interval: int,
    expires_at: float,
) -> str | None:
    """
    Poll GitHub for access token until authorized or expired.
    
    Args:
        device_code: Device code from request_device_code()
        interval: Polling interval in seconds
        expires_at: Unix timestamp when device code expires
    
    Returns:
        Access token string if successful, None if failed
    
    Handles these error codes:
    - authorization_pending: User hasn't authorized yet, keep polling
    - slow_down: Increase interval (handled by respecting GitHub's interval)
    - expired_token: Device code expired
    - access_denied: User declined authorization
    """
    url = "https://github.com/login/oauth/access_token"
    headers = {
        "Accept": "application/json",
    }
    data = {
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }
    
    async with httpx.AsyncClient() as client:
        while time.time() < expires_at:
            response = await client.post(url, data=data, headers=headers)
            
            if response.status_code != 200:
                logger.error(f"Failed to poll for token: {response.status_code}")
                return None
            
            result = response.json()
            
            # Check for errors
            if "error" in result:
                error = result["error"]
                
                if error == "authorization_pending":
                    # User hasn't authorized yet, keep waiting
                    await asyncio.sleep(interval)
                    continue
                
                elif error == "slow_down":
                    # GitHub wants us to slow down
                    await asyncio.sleep(interval + 5)
                    continue
                
                elif error == "expired_token":
                    console.print("[red]Device code expired. Please try again.[/red]")
                    return None
                
                elif error == "access_denied":
                    console.print("[red]Authorization denied by user.[/red]")
                    return None
                
                else:
                    console.print(f"[red]OAuth error: {error}[/red]")
                    logger.error(f"OAuth error: {result}")
                    return None
            
            # Success!
            if "access_token" in result:
                return result["access_token"]
            
            # Unexpected response
            logger.warning(f"Unexpected OAuth response: {result}")
            await asyncio.sleep(interval)
    
    console.print("[red]Device code expired (timeout).[/red]")
    return None


async def verify_copilot_access(github_token: str) -> bool:
    """
    Verify that the GitHub token has access to Copilot.
    
    Args:
        github_token: GitHub OAuth or personal access token
    
    Returns:
        True if user has Copilot access, False otherwise
    """
    try:
        # Try to get a Copilot token - this will fail if user doesn't have access
        from nanobot.providers.github_copilot_token import exchange_github_token_for_copilot
        
        await exchange_github_token_for_copilot(github_token)
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403:
            console.print("[red]Error: No GitHub Copilot subscription found.[/red]")
            console.print("Please subscribe at: https://github.com/features/copilot")
        elif e.response.status_code == 401:
            console.print("[red]Error: Invalid GitHub token.[/red]")
        else:
            console.print(f"[red]Error verifying Copilot access: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error verifying Copilot access: {e}[/red]")
        return False


async def login_github_copilot(open_browser: bool = True) -> str | None:
    """
    Authenticate with GitHub Copilot using OAuth Device Flow.
    
    This function:
    1. Requests a device code from GitHub
    2. Displays the user code in a Rich panel
    3. Optionally opens the browser to the verification URL
    4. Polls for the access token
    5. Returns the GitHub token
    
    Args:
        open_browser: If True, automatically open the browser
    
    Returns:
        GitHub access token if successful, None if failed
    """
    console.print("\n[bold cyan]GitHub Copilot Login[/bold cyan]\n")
    
    try:
        # Step 1: Request device code
        with console.status("[cyan]Requesting device code...[/cyan]"):
            device_data = await request_device_code()
        
        device_code = device_data["device_code"]
        user_code = device_data["user_code"]
        verification_uri = device_data["verification_uri"]
        expires_in = device_data["expires_in"]
        interval = device_data.get("interval", 5)
        
        # Step 2: Display user code in a nice panel
        code_text = Text()
        code_text.append("Enter this code: ", style="white")
        code_text.append(user_code, style="bold yellow")
        
        panel = Panel(
            code_text,
            title="[bold]GitHub Device Authorization[/bold]",
            subtitle=f"[dim]{verification_uri}[/dim]",
            border_style="cyan",
            padding=(1, 2),
        )
        console.print(panel)
        
        # Step 3: Open browser (optional)
        if open_browser:
            try:
                console.print(f"[dim]Opening browser to {verification_uri}...[/dim]\n")
                webbrowser.open(verification_uri)
            except Exception as e:
                logger.debug(f"Failed to open browser: {e}")
        else:
            console.print(f"\n[dim]Visit: {verification_uri}[/dim]\n")
        
        # Step 4: Poll for access token
        expires_at = time.time() + expires_in
        console.print("[cyan]Waiting for authorization...[/cyan]")
        
        with console.status("[cyan]Polling for token...[/cyan]"):
            github_token = await poll_for_access_token(device_code, interval, expires_at)
        
        if github_token:
            console.print("[green]✓ Authentication successful![/green]\n")
            return github_token
        else:
            console.print("[red]Authentication failed.[/red]\n")
            return None
    
    except httpx.HTTPStatusError as e:
        console.print(f"[red]HTTP error: {e.response.status_code}[/red]")
        logger.error(f"OAuth HTTP error: {e}")
        return None
    except Exception as e:
        console.print(f"[red]Error during authentication: {e}[/red]")
        logger.error(f"OAuth error: {e}")
        return None
