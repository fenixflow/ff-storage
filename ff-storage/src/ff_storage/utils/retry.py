"""
Retry utilities with exponential backoff and circuit breaker patterns.

This module provides decorators and utilities for handling transient failures
with automatic retry logic and circuit breaker protection.
"""

import asyncio
import functools
import logging
import random
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union

from ..exceptions import CircuitBreakerOpen


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.

    The circuit breaker has three states:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls are rejected immediately
    - HALF_OPEN: Testing if service recovered, limited calls allowed
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Type[Exception] = Exception,
        name: Optional[str] = None,
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before attempting recovery
            expected_exception: Exception types to count as failures
            name: Optional name for logging
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.name = name or "CircuitBreaker"

        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
        self.logger = logging.getLogger(__name__)

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.logger.info(f"{self.name}: Attempting reset (half-open)")
            else:
                reset_in = self.recovery_timeout - (datetime.now() - self.last_failure_time).seconds
                raise CircuitBreakerOpen(
                    service=self.name, failure_count=self.failure_count, reset_timeout=reset_in
                )

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise

    async def async_call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute async function through circuit breaker."""
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.logger.info(f"{self.name}: Attempting reset (half-open)")
            else:
                reset_in = self.recovery_timeout - (datetime.now() - self.last_failure_time).seconds
                raise CircuitBreakerOpen(
                    service=self.name, failure_count=self.failure_count, reset_timeout=reset_in
                )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        return (
            self.last_failure_time
            and (datetime.now() - self.last_failure_time).seconds >= self.recovery_timeout
        )

    def _on_success(self):
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.logger.info(f"{self.name}: Circuit recovered (closed)")
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def _on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.logger.warning(f"{self.name}: Circuit opened after {self.failure_count} failures")

    def reset(self):
        """Manually reset the circuit breaker."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        self.logger.info(f"{self.name}: Circuit manually reset")

    @property
    def is_open(self) -> bool:
        """Check if circuit is open."""
        return self.state == CircuitState.OPEN

    @property
    def status(self) -> Dict[str, Any]:
        """Get current circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "threshold": self.failure_threshold,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }


def exponential_backoff(
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
) -> Callable:
    """
    Calculate exponential backoff delay.

    Args:
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        jitter: Add random jitter to prevent thundering herd

    Returns:
        Function that calculates delay for given attempt number
    """

    def calculate_delay(attempt: int) -> float:
        delay = min(base_delay * (exponential_base**attempt), max_delay)
        if jitter:
            # Add jitter: random value between 0 and 25% of delay
            delay = delay * (1 + random.random() * 0.25)
        return delay

    return calculate_delay


def retry(
    max_attempts: int = 3,
    delay: Union[float, Callable[[int], float]] = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Callable:
    """
    Decorator for automatic retry with configurable backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Fixed delay or function that returns delay for attempt number
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback called before each retry
        circuit_breaker: Optional circuit breaker to use

    Example:
        @retry(max_attempts=3, delay=exponential_backoff())
        def unstable_operation():
            # Code that might fail transiently
            pass
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    if circuit_breaker:
                        return circuit_breaker.call(func, *args, **kwargs)
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        # Last attempt, re-raise
                        raise

                    if on_retry:
                        on_retry(e, attempt + 1)

                    # Calculate delay
                    sleep_time = delay(attempt) if callable(delay) else delay
                    time.sleep(sleep_time)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    if circuit_breaker:
                        return await circuit_breaker.async_call(func, *args, **kwargs)
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        # Last attempt, re-raise
                        raise

                    if on_retry:
                        on_retry(e, attempt + 1)

                    # Calculate delay
                    sleep_time = delay(attempt) if callable(delay) else delay
                    await asyncio.sleep(sleep_time)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def retry_async(
    max_attempts: int = 3,
    delay: Union[float, Callable[[int], float]] = 1.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Callable:
    """
    Async-specific retry decorator.

    This is an alias for retry() that makes it clear the decorated
    function should be async.
    """
    return retry(
        max_attempts=max_attempts,
        delay=delay,
        exceptions=exceptions,
        on_retry=on_retry,
        circuit_breaker=circuit_breaker,
    )


class RetryPolicy:
    """
    Configurable retry policy for reuse across multiple operations.

    Example:
        database_retry = RetryPolicy(
            max_attempts=5,
            delay=exponential_backoff(base_delay=0.5),
            exceptions=(DatabaseError, ConnectionError)
        )

        @database_retry
        async def query_database():
            # Database operation
            pass
    """

    def __init__(
        self,
        max_attempts: int = 3,
        delay: Union[float, Callable[[int], float]] = 1.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ):
        self.max_attempts = max_attempts
        self.delay = delay
        self.exceptions = exceptions
        self.on_retry = on_retry
        self.circuit_breaker = circuit_breaker

    def __call__(self, func: Callable) -> Callable:
        """Apply retry policy to function."""
        return retry(
            max_attempts=self.max_attempts,
            delay=self.delay,
            exceptions=self.exceptions,
            on_retry=self.on_retry,
            circuit_breaker=self.circuit_breaker,
        )(func)


# Pre-configured retry policies for common scenarios
DEFAULT_RETRY = RetryPolicy(
    max_attempts=3,
    delay=exponential_backoff(base_delay=1.0),
)

DATABASE_RETRY = RetryPolicy(
    max_attempts=5,
    delay=exponential_backoff(base_delay=0.5, max_delay=30.0),
)

NETWORK_RETRY = RetryPolicy(
    max_attempts=5,
    delay=exponential_backoff(base_delay=2.0, max_delay=60.0),
)
