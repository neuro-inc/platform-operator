from base64 import b64encode
from unittest import mock

import pytest

from platform_operator.consul_client import ConsulClient
from platform_operator.operator import (
    LOCK_KEY,
    end_operator_deployment,
    start_operator_deployment,
)


class TestStartOperatorDeployment:
    @pytest.fixture
    def consul_client(self) -> mock.AsyncMock:
        return mock.AsyncMock(ConsulClient)

    @pytest.mark.asyncio
    async def test_on_install(self, consul_client: mock.AsyncMock) -> None:
        await start_operator_deployment(consul_client, 1)

        consul_client.wait_healthy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_upgrade(self, consul_client: mock.AsyncMock) -> None:
        consul_client.create_session.return_value = "test"

        await start_operator_deployment(consul_client, 2)

        consul_client.wait_healthy.assert_awaited_once()
        consul_client.create_session.assert_awaited_once()
        consul_client.acquire_lock.assert_awaited_once_with(
            LOCK_KEY, b"platform-operator-2", session_id="test", sleep_s=mock.ANY
        )


class TestEndOperatorDeployment:
    @pytest.fixture
    def consul_client(self) -> mock.AsyncMock:
        return mock.AsyncMock(ConsulClient)

    @pytest.mark.asyncio
    async def test_on_install(self, consul_client: mock.AsyncMock) -> None:
        await end_operator_deployment(consul_client, 1)

        consul_client.wait_healthy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_upgrade_lock_released(
        self, consul_client: mock.AsyncMock
    ) -> None:
        lock_value = b"platform-operator-2"
        consul_client.get_key.return_value = [
            {"Session": "test", "Value": b64encode(lock_value).decode()}
        ]

        await end_operator_deployment(consul_client, 2)

        consul_client.wait_healthy.assert_awaited_once()
        consul_client.get_key.assert_awaited_once_with(LOCK_KEY)
        consul_client.release_lock.assert_awaited_once_with(
            LOCK_KEY, lock_value, session_id="test"
        )

    @pytest.mark.asyncio
    async def test_on_upgrade_expired_session_ignored(
        self, consul_client: mock.AsyncMock
    ) -> None:
        consul_client.get_key.return_value = [
            {"Session": "test", "Value": b64encode(b"cluster-config-updated").decode()}
        ]

        await end_operator_deployment(consul_client, 2)

        consul_client.wait_healthy.assert_awaited_once()
        consul_client.get_key.assert_awaited_once_with(LOCK_KEY)
        consul_client.delete_session.assert_not_awaited()
