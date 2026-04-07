"""
Caching and Performance Optimization Layer

Provides sophisticated caching mechanisms with multiple eviction policies,
compression support, and performance optimization.

Features:
- Multiple cache backends
- LRU, LFU, FIFO eviction policies
- Compression support
- TTL-based expiration
- Cache statistics
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Tuple
import zlib
import logging

logger = logging.getLogger(__name__)


class EvictionPolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    FIFO = "fifo"  # First In First Out


@dataclass
class CacheEntry:
    """Represents a cache entry."""
    key: str
    value: Any
    created_at: datetime
    accessed_at: datetime
    access_count: int = 0
    ttl: Optional[int] = None  # Time to live in seconds
    compressed: bool = False
    
    def is_expired(self) -> bool:
        """Check if entry has expired.
        
        Returns:
            True if expired, False otherwise
        """
        if self.ttl is None:
            return False
        
        expiry_time = self.created_at + timedelta(seconds=self.ttl)
        return datetime.utcnow() > expiry_time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "key": self.key,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "access_count": self.access_count,
            "ttl": self.ttl,
            "compressed": self.compressed,
        }


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    async def clear(self) -> int:
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        pass


class InMemoryCache(CacheBackend):
    """In-memory cache implementation."""
    
    def __init__(
        self,
        max_size: int = 1000,
        eviction_policy: EvictionPolicy = EvictionPolicy.LRU,
        enable_compression: bool = False,
        compression_level: int = 6,
    ):
        """Initialize in-memory cache.
        
        Args:
            max_size: Maximum number of entries
            eviction_policy: Eviction policy to use
            enable_compression: Enable compression for values
            compression_level: Compression level (1-9)
        """
        self.max_size = max_size
        self.eviction_policy = eviction_policy
        self.enable_compression = enable_compression
        self.compression_level = compression_level
        self.cache: Dict[str, CacheEntry] = {}
        self.lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        async with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            entry = self.cache[key]
            
            # Check if expired
            if entry.is_expired():
                del self.cache[key]
                self.misses += 1
                return None
            
            # Update access info
            entry.accessed_at = datetime.utcnow()
            entry.access_count += 1
            self.hits += 1
            
            # Decompress if needed
            value = entry.value
            if entry.compressed:
                try:
                    value = zlib.decompress(value)
                except Exception as e:
                    logger.error(f"Failed to decompress cache entry: {e}")
                    return None
            
            return value
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        async with self.lock:
            # Compress if enabled
            compressed = False
            if self.enable_compression:
                try:
                    value = zlib.compress(value, self.compression_level)
                    compressed = True
                except Exception as e:
                    logger.warning(f"Failed to compress cache value: {e}")
            
            # Create cache entry
            entry = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                accessed_at=datetime.utcnow(),
                ttl=ttl,
                compressed=compressed,
            )
            
            # Check if we need to evict
            if len(self.cache) >= self.max_size and key not in self.cache:
                await self._evict_one()
            
            self.cache[key] = entry
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted, False if not found
        """
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False
    
    async def clear(self) -> int:
        """Clear all cache entries.
        
        Returns:
            Number of entries cleared
        """
        async with self.lock:
            count = len(self.cache)
            self.cache.clear()
            return count
    
    async def _evict_one(self) -> None:
        """Evict one entry based on policy."""
        if not self.cache:
            return
        
        if self.eviction_policy == EvictionPolicy.LRU:
            # Evict least recently used
            key_to_evict = min(
                self.cache.keys(),
                key=lambda k: self.cache[k].accessed_at
            )
        elif self.eviction_policy == EvictionPolicy.LFU:
            # Evict least frequently used
            key_to_evict = min(
                self.cache.keys(),
                key=lambda k: self.cache[k].access_count
            )
        else:  # FIFO
            # Evict first in
            key_to_evict = min(
                self.cache.keys(),
                key=lambda k: self.cache[k].created_at
            )
        
        del self.cache[key_to_evict]
        self.evictions += 1
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with statistics
        """
        async with self.lock:
            total_requests = self.hits + self.misses
            hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
            
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": hit_rate,
                "evictions": self.evictions,
                "total_requests": total_requests,
            }


class CacheManager:
    """Manages caching across the system."""
    
    def __init__(
        self,
        max_size: int = 1000,
        eviction_policy: EvictionPolicy = EvictionPolicy.LRU,
        enable_compression: bool = False,
    ):
        """Initialize cache manager.
        
        Args:
            max_size: Maximum cache size
            eviction_policy: Eviction policy
            enable_compression: Enable compression
        """
        self.cache = InMemoryCache(
            max_size=max_size,
            eviction_policy=eviction_policy,
            enable_compression=enable_compression,
        )
        self.namespaces: Dict[str, InMemoryCache] = {}
    
    async def get(self, key: str, namespace: Optional[str] = None) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            namespace: Optional namespace
            
        Returns:
            Cached value or None
        """
        cache = self.namespaces.get(namespace) if namespace else self.cache
        return await cache.get(key)
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: Optional[str] = None,
    ) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
            namespace: Optional namespace
        """
        cache = self.namespaces.get(namespace) if namespace else self.cache
        await cache.set(key, value, ttl)
    
    async def delete(self, key: str, namespace: Optional[str] = None) -> bool:
        """Delete value from cache.
        
        Args:
            key: Cache key
            namespace: Optional namespace
            
        Returns:
            True if deleted
        """
        cache = self.namespaces.get(namespace) if namespace else self.cache
        return await cache.delete(key)
    
    async def clear(self, namespace: Optional[str] = None) -> int:
        """Clear cache entries.
        
        Args:
            namespace: Optional namespace (clears all if not specified)
            
        Returns:
            Number of entries cleared
        """
        if namespace:
            if namespace in self.namespaces:
                return await self.namespaces[namespace].clear()
            return 0
        else:
            total = await self.cache.clear()
            for ns_cache in self.namespaces.values():
                total += await ns_cache.clear()
            return total
    
    async def create_namespace(
        self,
        namespace: str,
        max_size: int = 1000,
    ) -> None:
        """Create a new cache namespace.
        
        Args:
            namespace: Namespace name
            max_size: Maximum size for namespace
        """
        self.namespaces[namespace] = InMemoryCache(max_size=max_size)
    
    async def get_stats(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Get cache statistics.
        
        Args:
            namespace: Optional namespace
            
        Returns:
            Dictionary with statistics
        """
        if namespace:
            cache = self.namespaces.get(namespace)
            if cache:
                return await cache.get_stats()
            return {}
        else:
            stats = {
                "main": await self.cache.get_stats(),
                "namespaces": {},
            }
            for ns_name, ns_cache in self.namespaces.items():
                stats["namespaces"][ns_name] = await ns_cache.get_stats()
            return stats


class CacheDecorator:
    """Decorator for caching function results."""
    
    def __init__(self, cache_manager: CacheManager, ttl: Optional[int] = None):
        """Initialize cache decorator.
        
        Args:
            cache_manager: CacheManager instance
            ttl: Time to live in seconds
        """
        self.cache_manager = cache_manager
        self.ttl = ttl
    
    def __call__(self, func):
        """Decorate function with caching.
        
        Args:
            func: Function to decorate
            
        Returns:
            Decorated function
        """
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"{func.__name__}:{args}:{kwargs}"
            
            # Try to get from cache
            cached_value = await self.cache_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Call function and cache result
            result = await func(*args, **kwargs)
            await self.cache_manager.set(cache_key, result, self.ttl)
            
            return result
        
        return wrapper
