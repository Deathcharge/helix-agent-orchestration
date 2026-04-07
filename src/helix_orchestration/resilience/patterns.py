"""
Resilience Patterns Module

Implements sophisticated resilience patterns including retry logic,
circuit breakers, rate limiting, and graceful degradation.

Features:
- Exponential backoff retry
- Circuit breaker pattern
- Rate limiting
- Bulkhead pattern
- Graceful degradation
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: int = 60
    half_open_max_calls: int = 3


class RetryPolicy:
    """Implements retry logic with exponential backoff."""
    
    def __init__(self, config: RetryConfig = None):
        """Initialize retry policy.
        
        Args:
            config: Retry configuration
        """
        self.config = config or RetryConfig()
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all retries fail
        """
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < self.config.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.config.max_retries + 1} attempts failed")
        
        raise last_exception
    
    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt.
        
        Args:
            attempt: Attempt number (0-indexed)
            
        Returns:
            Delay in seconds
        """
        delay = self.config.initial_delay * (self.config.backoff_multiplier ** attempt)
        delay = min(delay, self.config.max_delay)
        
        if self.config.jitter:
            import random
            delay *= random.uniform(0.5, 1.5)
        
        return delay


class CircuitBreaker:
    """Implements circuit breaker pattern."""
    
    def __init__(self, config: CircuitBreakerConfig = None):
        """Initialize circuit breaker.
        
        Args:
            config: Circuit breaker configuration
        """
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker.
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self) -> None:
        """Handle successful call."""
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("Circuit breaker CLOSED")
    
    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.error("Circuit breaker OPEN (half-open test failed)")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error("Circuit breaker OPEN (failure threshold exceeded)")
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset.
        
        Returns:
            True if should attempt reset
        """
        if not self.last_failure_time:
            return True
        
        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.timeout


class RateLimiter:
    """Implements rate limiting using token bucket algorithm."""
    
    def __init__(self, requests: int = 1000, window: int = 60):
        """Initialize rate limiter.
        
        Args:
            requests: Number of requests allowed
            window: Time window in seconds
        """
        self.requests = requests
        self.window = window
        self.tokens = requests
        self.last_update = datetime.utcnow()
        self.lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """Try to acquire tokens.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if acquired, False otherwise
        """
        async with self.lock:
            self._refill_tokens()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    async def wait_for_token(self, tokens: int = 1) -> None:
        """Wait until tokens are available.
        
        Args:
            tokens: Number of tokens to wait for
        """
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)
    
    def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time."""
        now = datetime.utcnow()
        elapsed = (now - self.last_update).total_seconds()
        
        # Calculate tokens to add
        tokens_to_add = (elapsed / self.window) * self.requests
        self.tokens = min(self.requests, self.tokens + tokens_to_add)
        self.last_update = now


class BulkheadPattern:
    """Implements bulkhead pattern for resource isolation."""
    
    def __init__(self, max_concurrent: int = 10):
        """Initialize bulkhead.
        
        Args:
            max_concurrent: Maximum concurrent operations
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.active_count = 0
        self.total_count = 0
        self.lock = asyncio.Lock()
    
    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function within bulkhead.
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        async with self.semaphore:
            async with self.lock:
                self.active_count += 1
                self.total_count += 1
            
            try:
                return await func(*args, **kwargs)
            finally:
                async with self.lock:
                    self.active_count -= 1
    
    async def get_stats(self) -> Dict[str, int]:
        """Get bulkhead statistics.
        
        Returns:
            Dictionary with statistics
        """
        async with self.lock:
            return {
                "active": self.active_count,
                "total": self.total_count,
                "max_concurrent": self.max_concurrent,
            }


class GracefulDegradation:
    """Implements graceful degradation strategies."""
    
    def __init__(self):
        """Initialize graceful degradation."""
        self.degradation_level = 0  # 0 = normal, 1 = degraded, 2 = minimal
        self.fallback_handlers: Dict[str, Callable] = {}
    
    def register_fallback(self, operation: str, handler: Callable) -> None:
        """Register fallback handler for operation.
        
        Args:
            operation: Operation name
            handler: Fallback handler function
        """
        self.fallback_handlers[operation] = handler
    
    async def execute_with_fallback(
        self,
        operation: str,
        primary_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute with fallback support.
        
        Args:
            operation: Operation name
            primary_func: Primary function
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Result from primary or fallback function
        """
        try:
            return await primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary operation failed: {e}, attempting fallback")
            
            if operation in self.fallback_handlers:
                try:
                    return await self.fallback_handlers[operation](*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
                    raise
            else:
                raise
    
    def set_degradation_level(self, level: int) -> None:
        """Set system degradation level.
        
        Args:
            level: Degradation level (0-2)
        """
        self.degradation_level = min(max(level, 0), 2)
        logger.warning(f"System degradation level set to {self.degradation_level}")
    
    def is_degraded(self) -> bool:
        """Check if system is degraded.
        
        Returns:
            True if degraded
        """
        return self.degradation_level > 0


class ResilienceManager:
    """Manages all resilience patterns."""
    
    def __init__(self):
        """Initialize resilience manager."""
        self.retry_policy = RetryPolicy()
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = RateLimiter()
        self.bulkhead = BulkheadPattern()
        self.graceful_degradation = GracefulDegradation()
    
    async def execute_resilient(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with all resilience patterns.
        
        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        # Check rate limit
        await self.rate_limiter.wait_for_token()
        
        # Execute through circuit breaker and bulkhead
        async def wrapped():
            return await self.bulkhead.execute(func, *args, **kwargs)
        
        return await self.circuit_breaker.call(wrapped)
    
    async def get_resilience_stats(self) -> Dict[str, Any]:
        """Get resilience statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            "circuit_breaker": {
                "state": self.circuit_breaker.state.value,
                "failures": self.circuit_breaker.failure_count,
            },
            "bulkhead": await self.bulkhead.get_stats(),
            "degradation_level": self.graceful_degradation.degradation_level,
        }
