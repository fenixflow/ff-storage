#!/usr/bin/env python3
"""
Example demonstrating ff-logger usage in async applications.

Shows how ff-logger instances work seamlessly with asyncio,
including context preservation across async boundaries.

Created by Ben Moag (Fenixflow)
"""

import asyncio
import logging
import random

from ff_logger import ConsoleLogger, JSONLogger


async def main():
    # Create main application logger
    logger = ConsoleLogger(
        name="async_app", level=logging.INFO, context={"app": "data_processor", "mode": "async"}
    )

    logger.info("Starting async application")

    # Process multiple tasks concurrently
    tasks = []
    for i in range(5):
        # Create task-specific logger
        task_logger = logger.bind(task_id=f"task-{i}", worker_id=i)
        tasks.append(process_data(task_logger, i))

    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)

    logger.info("All tasks completed", total_results=sum(results))

    # Demonstrate async context manager pattern
    await process_with_timing(logger)


async def process_data(logger, task_num):
    """Simulate async data processing with logging."""
    logger.info("Starting data processing")

    # Simulate variable processing time
    processing_time = random.uniform(0.5, 2.0)
    await asyncio.sleep(processing_time)

    # Simulate some processing steps
    for step in range(3):
        step_logger = logger.bind(step=step)
        step_logger.debug(f"Processing step {step}")
        await asyncio.sleep(0.1)

    result = task_num * 10
    logger.info(
        "Data processing completed", processing_time=f"{processing_time:.2f}s", result=result
    )

    return result


async def process_with_timing(logger):
    """Demonstrate async context manager for timing operations."""

    class AsyncTimer:
        def __init__(self, logger, operation):
            self.logger = logger
            self.operation = operation
            self.start_time = None

        async def __aenter__(self):
            self.start_time = asyncio.get_event_loop().time()
            self.logger.info(f"Starting {self.operation}")
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            elapsed = asyncio.get_event_loop().time() - self.start_time
            if exc_type:
                self.logger.error(
                    f"{self.operation} failed", error=str(exc_val), elapsed=f"{elapsed:.3f}s"
                )
            else:
                self.logger.info(f"{self.operation} completed", elapsed=f"{elapsed:.3f}s")

    # Use the async context manager
    async with AsyncTimer(logger, "database_query"):
        await asyncio.sleep(0.5)  # Simulate database query

    async with AsyncTimer(logger, "api_call"):
        await asyncio.sleep(0.3)  # Simulate API call

    # Simulate an operation that fails
    try:
        async with AsyncTimer(logger, "risky_operation"):
            await asyncio.sleep(0.1)
            raise ValueError("Simulated error")
    except ValueError:
        pass  # Error already logged by context manager


async def concurrent_logging_demo():
    """Demonstrate thread-safe logging from multiple async tasks."""
    # JSON logger for structured async logging
    json_logger = JSONLogger(name="concurrent", level=logging.INFO, context={"test": "concurrency"})

    async def worker(worker_id, iterations):
        worker_logger = json_logger.bind(worker_id=worker_id)
        for i in range(iterations):
            worker_logger.info(f"Working on iteration {i}")
            await asyncio.sleep(random.uniform(0.01, 0.05))
        worker_logger.info("Worker completed")

    # Start multiple workers
    await asyncio.gather(
        worker("alpha", 5), worker("beta", 5), worker("gamma", 5), worker("delta", 5)
    )


if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())

    # Run concurrent logging demo
    print("\n--- Concurrent Logging Demo ---")
    asyncio.run(concurrent_logging_demo())
