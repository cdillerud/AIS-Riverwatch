# River Watch Backend - HTTP Client Service
# Shared HTTP client with connection pooling for external API calls

import httpx
from typing import Optional
import logging
import asyncio

logger = logging.getLogger(__name__)

# Shared HTTP client with connection pooling
_http_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client."""
    global _http_client
    
    async with _client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20,
                    keepalive_expiry=30.0
                ),
                follow_redirects=True
            )
            logger.info("HTTP client pool initialized")
    
    return _http_client


async def close_http_client():
    """Close the HTTP client (call on shutdown)."""
    global _http_client
    
    async with _client_lock:
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None
            logger.info("HTTP client pool closed")


async def fetch_with_retry(
    url: str, 
    method: str = "GET",
    retries: int = 3,
    retry_delay: float = 1.0,
    **kwargs
) -> Optional[httpx.Response]:
    """Fetch URL with automatic retry on failure."""
    client = await get_http_client()
    
    for attempt in range(retries):
        try:
            if method.upper() == "GET":
                response = await client.get(url, **kwargs)
            elif method.upper() == "POST":
                response = await client.post(url, **kwargs)
            else:
                response = await client.request(method, url, **kwargs)
            
            response.raise_for_status()
            return response
            
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            if attempt < retries - 1:
                logger.warning(f"HTTP request failed (attempt {attempt + 1}/{retries}): {e}")
                await asyncio.sleep(retry_delay * (attempt + 1))
            else:
                logger.error(f"HTTP request failed after {retries} attempts: {e}")
                return None
    
    return None
