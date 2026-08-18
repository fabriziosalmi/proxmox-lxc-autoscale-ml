"""Async API client for batch operations - High performance container config fetching."""
import asyncio
import aiohttp
import logging

class AsyncAPIClient:
    """
    Async HTTP client for batch API operations.

    Features:
    - Concurrent requests with asyncio.gather()
    - Connection pooling for better performance
    - Automatic retry with exponential backoff
    - Circuit breaker integration
    - Timeout management
    """

    def __init__(self, base_url: str, timeout: int = 5, max_concurrent: int = 10,
                 api_key: str | None = None):
        """
        Initialize async API client.

        Args:
            base_url: Base URL for API (e.g., http://127.0.0.1:5000)
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests
            api_key: Sent as X-API-Key. Required when the API has
                `authentication.enabled: true`; without it every request 401s.
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        """Context manager entry - create session."""
        connector = aiohttp.TCPConnector(
            limit=self.max_concurrent,
            limit_per_host=self.max_concurrent,
            ttl_dns_cache=300  # Cache DNS for 5 minutes
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self.timeout,
            headers={"X-API-Key": self.api_key} if self.api_key else None,
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        if self._session:
            await self._session.close()
            # Give time for connections to close
            await asyncio.sleep(0.1)

    @staticmethod
    def _backoff(attempt: int, retry_delay: int | None) -> int:
        """Exponential backoff, seeded from retry_logic.retry_delay when given.

        The delay was hard-coded, so `retry_logic.retry_delay` governed only
        apply_scaling despite the config documenting it for API calls generally.
        """
        base = 1 if retry_delay is None else max(1, int(retry_delay))
        return base * (2 ** attempt)

    async def fetch_container_config(
        self,
        container_id: str,
        retry_count: int = 3,
        circuit_breaker = None,
        retry_delay: int | None = None,
    ) -> tuple[str, dict | None]:
        """
        Fetch configuration for a single container with retry logic.

        Args:
            container_id: Container ID to fetch
            retry_count: Number of retry attempts
            circuit_breaker: Optional circuit breaker instance

        Returns:
            Tuple of (container_id, config_dict or None)
        """
        # Check circuit breaker
        if circuit_breaker and circuit_breaker.is_open(f"api_{container_id}"):
            logging.debug(f"Circuit breaker open for container {container_id}, skipping API call")
            return (container_id, None)

        url = f"{self.base_url}/resource/lxc/config?lxc_id={container_id}"

        async with self.semaphore:  # Limit concurrent requests
            for attempt in range(retry_count):
                try:
                    async with self._session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            config = data.get('data', {})

                            # Record success in circuit breaker
                            if circuit_breaker:
                                circuit_breaker.record_success(f"api_{container_id}")

                            return (container_id, config)

                        elif response.status >= 500:
                            # Server error - retry
                            if attempt < retry_count - 1:
                                wait_time = self._backoff(attempt, retry_delay)
                                logging.warning(
                                    f"Server error {response.status} for container {container_id}, "
                                    f"retry {attempt + 1}/{retry_count} in {wait_time}s"
                                )
                                await asyncio.sleep(wait_time)
                            else:
                                logging.error(
                                    f"Failed to fetch config for container {container_id} "
                                    f"after {retry_count} attempts: HTTP {response.status}"
                                )
                                if circuit_breaker:
                                    circuit_breaker.record_failure(f"api_{container_id}")
                                return (container_id, None)
                        elif response.status in (401, 403):
                            # Retrying cannot help, and the generic "client
                            # error" wording sent operators looking in the
                            # wrong place while autoscaling silently stopped.
                            logging.error(
                                f"The API rejected our credentials (HTTP {response.status}). "
                                f"It has authentication.enabled: true; set `api.api_key` in "
                                f"the model configuration to one of its `authentication.api_keys`."
                            )
                            return (container_id, None)
                        else:
                            # Client error - don't retry
                            logging.warning(
                                f"Client error {response.status} for container {container_id}"
                            )
                            return (container_id, None)

                except asyncio.TimeoutError:
                    if attempt < retry_count - 1:
                        logging.warning(
                            f"Timeout fetching container {container_id}, "
                            f"retry {attempt + 1}/{retry_count}"
                        )
                        await asyncio.sleep(self._backoff(attempt, retry_delay))
                    else:
                        logging.error(
                            f"Timeout fetching container {container_id} after {retry_count} attempts"
                        )
                        if circuit_breaker:
                            circuit_breaker.record_failure(f"api_{container_id}")
                        return (container_id, None)

                except aiohttp.ClientError as e:
                    if attempt < retry_count - 1:
                        logging.warning(
                            f"Network error for container {container_id}: {e}, "
                            f"retry {attempt + 1}/{retry_count}"
                        )
                        await asyncio.sleep(self._backoff(attempt, retry_delay))
                    else:
                        logging.error(
                            f"Network error for container {container_id} after "
                            f"{retry_count} attempts: {e}"
                        )
                        if circuit_breaker:
                            circuit_breaker.record_failure(f"api_{container_id}")
                        return (container_id, None)

        return (container_id, None)

    async def fetch_batch_configs(
        self,
        container_ids: list[str],
        circuit_breaker = None,
        retry_count: int = 3,
        retry_delay: int | None = None,
    ) -> dict[str, dict | None]:
        """
        Fetch configurations for multiple containers concurrently.

        Args:
            container_ids: List of container IDs to fetch
            circuit_breaker: Optional circuit breaker instance

        Returns:
            Dict mapping container_id to config (or None if failed)
        """
        if not container_ids:
            return {}

        logging.info(f"Fetching configs for {len(container_ids)} containers in parallel")

        # Create tasks for all containers
        tasks = [
            self.fetch_container_config(cid, retry_count=retry_count,
                                        retry_delay=retry_delay,
                                        circuit_breaker=circuit_breaker)
            for cid in container_ids
        ]

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build result dictionary
        configs = {}
        for result in results:
            if isinstance(result, Exception):
                logging.error(f"Unexpected error in batch fetch: {result}")
                continue

            container_id, config = result
            configs[container_id] = config

        successful = sum(1 for c in configs.values() if c is not None)
        logging.info(
            f"Batch fetch completed: {successful}/{len(container_ids)} successful"
        )

        return configs


async def fetch_all_container_configs(
    container_ids: list[str],
    api_url: str,
    circuit_breaker = None,
    timeout: int = 5,
    max_concurrent: int = 10,
    api_key: str | None = None,
    retry_count: int = 3,
    retry_delay: int | None = None,
) -> dict[str, dict | None]:
    """
    Convenience function to fetch all container configs with proper session management.

    Args:
        container_ids: List of container IDs
        api_url: Base API URL
        circuit_breaker: Optional circuit breaker instance
        timeout: Request timeout in seconds
        max_concurrent: Maximum concurrent requests

    Returns:
        Dict mapping container_id to config
    """
    async with AsyncAPIClient(api_url, timeout, max_concurrent, api_key) as client:
        return await client.fetch_batch_configs(
            container_ids, circuit_breaker, retry_count=retry_count,
            retry_delay=retry_delay)


def fetch_container_configs_sync(
    container_ids: list[str],
    api_url: str,
    circuit_breaker = None,
    timeout: int = 5,
    max_concurrent: int = 10,
    api_key: str | None = None,
    retry_count: int = 3,
    retry_delay: int | None = None,
) -> dict[str, dict | None]:
    """
    Synchronous wrapper for async batch fetch - for use in sync code.

    Args:
        container_ids: List of container IDs
        api_url: Base API URL
        circuit_breaker: Optional circuit breaker instance
        timeout: Request timeout in seconds
        max_concurrent: Maximum concurrent requests

    Returns:
        Dict mapping container_id to config
    """
    try:
        # Try to use existing event loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is already running, create a new one in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    fetch_all_container_configs(
                        container_ids, api_url, circuit_breaker, timeout, max_concurrent, api_key,
                        retry_count, retry_delay
                    )
                )
                return future.result()
        else:
            # Use existing loop
            return loop.run_until_complete(
                fetch_all_container_configs(
                    container_ids, api_url, circuit_breaker, timeout, max_concurrent, api_key,
                        retry_count, retry_delay
                )
            )
    except RuntimeError:
        # No event loop, create new one
        return asyncio.run(
            fetch_all_container_configs(
                container_ids, api_url, circuit_breaker, timeout, max_concurrent, api_key,
                        retry_count, retry_delay
            )
        )
