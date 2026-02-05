# River Watch Backend - Cache Service
# TTL-based caching for expensive external API calls

from typing import Any, Optional, Callable, Dict
from datetime import datetime, timezone, timedelta
import asyncio
import logging
import hashlib
import json

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL-based cache for async operations."""
    
    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, dict] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()
        self._stats = {"hits": 0, "misses": 0}
    
    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from function args."""
        key_data = f"{prefix}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        async with self._lock:
            entry = self._cache.get(key)
            if not entry:
                self._stats["misses"] += 1
                return None
            
            if datetime.now(timezone.utc) > entry["expires_at"]:
                del self._cache[key]
                self._stats["misses"] += 1
                return None
            
            self._stats["hits"] += 1
            return entry["value"]
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in cache with TTL."""
        ttl = ttl or self._default_ttl
        async with self._lock:
            self._cache[key] = {
                "value": value,
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl),
                "created_at": datetime.now(timezone.utc)
            }
    
    async def delete(self, key: str) -> None:
        """Remove entry from cache."""
        async with self._lock:
            self._cache.pop(key, None)
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self._lock:
            self._cache.clear()
    
    async def cleanup(self) -> int:
        """Remove expired entries. Returns count of removed entries."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._cache.items() if now > v["expires_at"]]
            for k in expired:
                del self._cache[k]
            return len(expired)
    
    @property
    def stats(self) -> dict:
        """Get cache statistics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "entries": len(self._cache)
        }


# Global cache instances with different TTLs
usace_cache = TTLCache(default_ttl=60)      # 1 min for lock queue data
usgs_cache = TTLCache(default_ttl=300)      # 5 min for water conditions
locks_cache = TTLCache(default_ttl=3600)    # 1 hour for static lock info
stats_cache = TTLCache(default_ttl=60)      # 1 min for vessel stats


def cached(cache: TTLCache, ttl: Optional[int] = None, prefix: str = ""):
    """Decorator for caching async function results."""
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache._make_key(prefix or func.__name__, *args, **kwargs)
            
            # Try to get from cache
            cached_value = await cache.get(key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {prefix or func.__name__}")
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            await cache.set(key, result, ttl)
            logger.debug(f"Cache miss: {prefix or func.__name__}")
            return result
        
        return wrapper
    return decorator


async def get_cache_stats() -> dict:
    """Get statistics for all caches."""
    return {
        "usace": usace_cache.stats,
        "usgs": usgs_cache.stats,
        "locks": locks_cache.stats,
        "stats": stats_cache.stats
    }


async def clear_all_caches() -> None:
    """Clear all caches."""
    await usace_cache.clear()
    await usgs_cache.clear()
    await locks_cache.clear()
    await stats_cache.clear()
    logger.info("All caches cleared")
