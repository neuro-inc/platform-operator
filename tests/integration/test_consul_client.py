import asyncio
import collections.abc

import pytest

from platform_operator.consul_client import ConsulClient, SessionExpiredError


class TestConsulClient:
    @pytest.mark.asyncio
    async def test_get_key(self, consul_client: ConsulClient) -> None:
        assert await consul_client.put_key("key/1", b"value1")
        result = await consul_client.get_key("key/1")
        assert isinstance(result, collections.abc.Sequence)
        assert isinstance(result[0], dict)
        assert result[0]["Value"] == "dmFsdWUx"

        assert await consul_client.put_key("key/2", b"value2")
        result = await consul_client.get_key("key/2", raw=True)
        assert isinstance(result, bytes)
        assert result == b"value2"

        result = await consul_client.get_key("key", recurse=True)
        assert isinstance(result, collections.Sequence)
        assert isinstance(result[0], dict)
        assert isinstance(result[1], dict)
        assert result[0]["Value"] == "dmFsdWUx"
        assert result[1]["Value"] == "dmFsdWUy"

    @pytest.mark.asyncio
    async def test_delete_key(self, consul_client: ConsulClient) -> None:
        assert await consul_client.put_key("key", b"value")
        assert await consul_client.delete_key("key")

    @pytest.mark.asyncio
    async def test_get_sessions(self, consul_client: ConsulClient) -> None:
        session_id = await consul_client.create_session(ttl_s=10, name="test")
        result = await consul_client.get_sessions()

        assert any(r["ID"] == session_id and r["Name"] == "test" for r in result)

    @pytest.mark.asyncio
    async def test_delete_session(self, consul_client: ConsulClient) -> None:
        session_id = await consul_client.create_session(ttl_s=10, name="test")
        assert await consul_client.delete_session(session_id)

    @pytest.mark.asyncio
    async def test_sequential_lock(self, consul_client: ConsulClient) -> None:
        result = []
        i = 0

        await consul_client.delete_key("lock")

        async def run(delay_s: float) -> None:
            async with consul_client.lock_key(
                "lock", b"value", ttl_s=10, lock_delay_s=1, sleep_s=0.5, timeout_s=5
            ):
                nonlocal i
                i += 1
                result.append(f"{i} start")
                if delay_s:
                    await asyncio.sleep(delay_s)
                result.append(f"{i} end")

        await asyncio.wait(
            [
                run(delay_s=1),
                run(delay_s=0.5),
                run(delay_s=0),
            ]
        )

        assert result == ["1 start", "1 end", "2 start", "2 end", "3 start", "3 end"]

    @pytest.mark.asyncio
    async def test_expired_lock(self, consul_client: ConsulClient) -> None:
        await consul_client.delete_key("lock")

        async def run_expired() -> None:
            with pytest.raises(SessionExpiredError):
                async with consul_client.lock_key(
                    "lock", b"value", ttl_s=10, lock_delay_s=1
                ):
                    await asyncio.sleep(10.1)

        async def run() -> None:
            async with consul_client.lock_key(
                "lock", b"value", ttl_s=10, lock_delay_s=1
            ):
                pass

        asyncio.create_task(run_expired())

        await asyncio.sleep(1)
        await asyncio.wait_for(run(), 11.1)  # ttl + lock_delay + 0.1

    @pytest.mark.asyncio
    async def test_lock_raises_error(self, consul_client: ConsulClient) -> None:
        await consul_client.delete_key("lock")

        async def run_raise() -> None:
            async with consul_client.lock_key(
                "lock", b"value", ttl_s=10, lock_delay_s=1
            ):
                raise Exception("error inside lock")

        async def run() -> None:
            async with consul_client.lock_key(
                "lock", b"value", ttl_s=10, lock_delay_s=1, timeout_s=1.1
            ):
                pass

        with pytest.raises(Exception, match="error inside lock"):
            await run_raise()

        # lock should be immediately released after exception

        await asyncio.wait_for(run(), 1.1)  # lock_delay + 0.1
