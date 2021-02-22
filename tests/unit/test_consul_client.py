from typing import Iterator
from unittest import mock

import aiohttp
import pytest
from yarl import URL

from platform_operator.consul_client import ConsulClient


pytestmark = pytest.mark.usefixtures(
    "create_session", "create_session", "get_key", "put_key"
)


@pytest.fixture
def create_session() -> Iterator[mock.AsyncMock]:
    with mock.patch(
        "platform_operator.consul_client.ConsulClient.create_session"
    ) as mocked:
        yield mocked


@pytest.fixture
def delete_session() -> Iterator[mock.AsyncMock]:
    with mock.patch(
        "platform_operator.consul_client.ConsulClient.delete_session"
    ) as mocked:
        yield mocked


@pytest.fixture
def get_key() -> Iterator[mock.AsyncMock]:
    with mock.patch("platform_operator.consul_client.ConsulClient.get_key") as mocked:
        yield mocked


@pytest.fixture
def put_key() -> Iterator[mock.AsyncMock]:
    with mock.patch("platform_operator.consul_client.ConsulClient.put_key") as mocked:
        yield mocked


class TestConsulClient:
    @pytest.fixture
    def consul_client(self) -> ConsulClient:
        return ConsulClient(URL("localhost"))

    @pytest.mark.asyncio
    async def test_lock_key(
        self,
        consul_client: ConsulClient,
        create_session: mock.AsyncMock,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
        put_key: mock.AsyncMock,
    ) -> None:
        async with consul_client.lock_key("key", b"value", session_ttl_s=10):
            pass

        create_session.assert_awaited_once()
        put_key.assert_awaited_once()
        get_key.assert_awaited_once()
        delete_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_key_create_session_errors_ignored(
        self,
        consul_client: ConsulClient,
        create_session: mock.AsyncMock,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
        put_key: mock.AsyncMock,
    ) -> None:
        create_session.side_effect = [aiohttp.ClientError, None]

        async with consul_client.lock_key("key", b"value", session_ttl_s=10):
            pass

        create_session.assert_awaited()
        put_key.assert_awaited_once()
        get_key.assert_awaited_once()
        delete_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_key_put_key_errors_ignored(
        self,
        consul_client: ConsulClient,
        create_session: mock.AsyncMock,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
        put_key: mock.AsyncMock,
    ) -> None:
        put_key.side_effect = [aiohttp.ClientError, True]

        async with consul_client.lock_key("key", b"value", session_ttl_s=10):
            pass

        create_session.assert_awaited_once()
        put_key.assert_awaited()
        get_key.assert_awaited_once()
        delete_session.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_release_lock_already_released(
        self,
        consul_client: ConsulClient,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
    ) -> None:
        get_key.return_value = [{"Session": ""}]

        await consul_client.release_lock("key", b"value", session_id="test")

        get_key.assert_awaited_once()
        delete_session.assert_awaited_once_with("test")

    @pytest.mark.asyncio
    async def test_release_lock_key_not_found(
        self,
        consul_client: ConsulClient,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
    ) -> None:
        get_key.side_effect = aiohttp.ClientResponseError(
            mock.Mock(), mock.Mock(), status=404
        )

        await consul_client.release_lock("key", b"value", session_id="test")

        get_key.assert_awaited_once()
        delete_session.assert_awaited_once_with("test")

    @pytest.mark.asyncio
    async def test_release_lock_get_key_errors_ignored(
        self,
        consul_client: ConsulClient,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
    ) -> None:
        get_key.return_value = [aiohttp.ClientError, [{"Session": ""}]]

        await consul_client.release_lock("key", b"value", session_id="test")

        get_key.assert_awaited()
        delete_session.assert_awaited_once_with("test")

    @pytest.mark.asyncio
    async def test_release_lock_put_key_errors_ignored(
        self,
        consul_client: ConsulClient,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
        put_key: mock.AsyncMock,
    ) -> None:
        get_key.side_effect = [[{"Session": "test"}], [{"Session": ""}]]

        await consul_client.release_lock("key", b"value", session_id="test")

        get_key.assert_awaited()
        put_key.assert_awaited_once_with("key", b"value", release="test")
        delete_session.assert_awaited_once_with("test")

    @pytest.mark.asyncio
    async def test_release_lock_delete_session_errors_ignored(
        self,
        consul_client: ConsulClient,
        delete_session: mock.AsyncMock,
        get_key: mock.AsyncMock,
    ) -> None:
        delete_session.side_effect = [aiohttp.ClientError, True]

        await consul_client.release_lock("key", b"value", session_id="test")

        get_key.assert_awaited_once()
        delete_session.assert_awaited_with("test")
