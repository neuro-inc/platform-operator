import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Union

import aiohttp
import aiohttp.web
from yarl import URL


logger = logging.getLogger(__name__)


class SessionExpiredError(Exception):
    pass


class ConsulClient:
    def __init__(
        self,
        url: Union[str, URL],
        trace_configs: Optional[List[aiohttp.TraceConfig]] = None,
    ) -> None:
        self._url = URL(url)
        self._trace_configs = trace_configs
        self._client: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "ConsulClient":
        self._client = aiohttp.ClientSession(trace_configs=self._trace_configs)
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.close()

    async def close(self) -> None:
        assert self._client
        await self._client.close()

    async def wait_healthy(self, sleep_s: float = 0.1) -> None:
        assert self._client
        logger.info("Waiting until Consul is healthy")
        while True:
            async with self._client.get(
                self._url / "v1/status/leader", timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status < 400:
                    text = await response.text()
                    if re.search(r"\".+\"", text):
                        break
            await asyncio.sleep(sleep_s)

    async def get_key(
        self, key: str, *, recurse: bool = False, raw: bool = False
    ) -> Union[Sequence[Dict[str, Any]], bytes]:
        assert self._client
        query = {}
        if recurse:
            query["recurse"] = "true"
        if raw:
            query["raw"] = "true"
        async with self._client.get(
            (self._url / "v1/kv" / key).with_query(query or None)
        ) as response:
            response.raise_for_status()
            if raw:
                return await response.read()
            payload = await response.json()
            return payload

    async def put_key(
        self, key: str, value: bytes, *, acquire: str = "", release: str = ""
    ) -> bool:
        assert self._client
        query = {}
        if acquire:
            query["acquire"] = acquire
        if release:
            query["release"] = release
        async with self._client.put(
            (self._url / "v1/kv" / key).with_query(query or None), data=value
        ) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    async def delete_key(self, key: str) -> bool:
        assert self._client
        async with self._client.delete(self._url / "v1/kv" / key) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    async def get_sessions(self) -> Sequence[Dict[str, Any]]:
        assert self._client
        async with self._client.get(self._url / "v1/session/list") as response:
            response.raise_for_status()
            payload = await response.json()
            return payload

    async def create_session(
        self,
        *,
        ttl_s: int,
        lock_delay_s: Optional[int] = None,
        name: str = "",
        behavior: str = "",
    ) -> str:
        assert self._client
        assert ttl_s >= 10
        assert not lock_delay_s or lock_delay_s > 0
        payload = {"TTL": f"{ttl_s}s"}
        if name:
            payload["Name"] = name
        if behavior:
            payload["Behavior"] = behavior
        if lock_delay_s:
            payload["LockDelay"] = f"{lock_delay_s}s"
        async with self._client.put(
            self._url / "v1/session/create", json=payload
        ) as response:
            response.raise_for_status()
            payload = await response.json()
            return payload["ID"]

    async def delete_session(self, session_id: str) -> bool:
        assert self._client
        async with self._client.put(
            self._url / "v1/session/destroy" / session_id
        ) as response:
            response.raise_for_status()
            text = await response.text()
            return text.strip() == "true"

    @asynccontextmanager
    async def lock_key(
        self,
        key: str,
        value: bytes,
        *,
        session_ttl_s: int,
        lock_delay_s: Optional[int] = None,
        sleep_s: float = 0.1,
        timeout_s: Optional[float] = None,
    ) -> AsyncIterator[None]:
        attempt = 0
        while True:
            try:
                session_id = await self.create_session(
                    ttl_s=session_ttl_s, lock_delay_s=lock_delay_s
                )
                logger.info("Session %r created", session_id)
                break
            except aiohttp.ClientError as exc:
                logger.warning("Consul failed with temporary error", exc_info=exc)
                await self._backoff_sleep(attempt)
            attempt += 1

        try:
            acquire_lock_future = self.acquire_lock(
                key, value, session_id=session_id, sleep_s=sleep_s
            )
            if timeout_s:
                await asyncio.wait_for(acquire_lock_future, timeout_s)
            else:
                await acquire_lock_future
            start_time = time.monotonic()  # lock start time
            yield
            elapsed_s = time.monotonic() - start_time
            if elapsed_s >= session_ttl_s:
                logger.warning("Lock (%r, %r) expired", session_id, key)
                raise SessionExpiredError(f"Session {session_id!r} expired")
        finally:
            await self.release_lock(key, value, session_id=session_id)

    async def acquire_lock(
        self,
        key: str,
        value: bytes,
        *,
        session_id: str,
        sleep_s: float = 0.1,
    ) -> None:
        while True:
            try:
                acquired = await self.put_key(key, value, acquire=session_id)
                if acquired:
                    logger.info("Lock (%r, %r) acquired", session_id, key)
                    return
                logger.info("Lock (%r, %r) was not acquired", session_id, key)
            except aiohttp.ClientError as exc:
                logger.warning("Consul failed with temporary error", exc_info=exc)
            await asyncio.sleep(sleep_s)

    async def release_lock(self, key: str, value: bytes, *, session_id: str) -> None:
        try:
            attempt = 0
            while True:
                try:
                    # Check lock has already been released
                    try:
                        metadata = await self.get_key(key)
                    except aiohttp.ClientResponseError as exc:
                        if exc.status != aiohttp.web.HTTPNotFound.status_code:
                            raise
                        metadata = [{}]
                    assert isinstance(metadata[0], dict)
                    if metadata and metadata[0].get("Session", "") != session_id:
                        return

                    released = await self.put_key(key, value, release=session_id)
                    if released:
                        logger.info("Lock (%r, %r) released", session_id, key)
                        return
                except aiohttp.ClientError as exc:
                    logger.warning("Consul failed with temporary error", exc_info=exc)
                    await self._backoff_sleep(attempt)
                attempt += 1
        finally:
            attempt = 0
            while True:
                try:
                    # delete is idempotent, always returns 200
                    await self.delete_session(session_id)
                    logger.info("Session %r destroyed", session_id)
                    return
                except aiohttp.ClientError as exc:
                    logger.warning("Consul failed with temporary error", exc_info=exc)
                    await self._backoff_sleep(attempt)
                attempt += 1

    async def _backoff_sleep(self, attempt: int) -> None:
        delay_s = min(0.1 * 2 ** attempt, 60)
        await asyncio.sleep(delay_s)
