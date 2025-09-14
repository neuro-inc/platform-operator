from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest import mock

import pytest

from platform_operator.kube_client import (
    KubeClient,
    PlatformPhase,
    PlatformStatusManager,
)


pytestmark = pytest.mark.asyncio


class TestPlatformStatusManager:
    @pytest.fixture
    def kube_client(self) -> mock.AsyncMock:
        return mock.AsyncMock(KubeClient)

    @pytest.fixture
    def manager(self, kube_client: KubeClient) -> PlatformStatusManager:
        return PlatformStatusManager(kube_client, namespace="default")

    @pytest.fixture
    def status(self) -> dict[str, Any]:
        return {
            "phase": "Deployed",
            "retries": 0,
        }

    async def test_get_pending_phase(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
    ) -> None:
        kube_client.get_platform_status.return_value = None

        phase = await manager.get_phase("neuro")

        assert phase == PlatformPhase.PENDING

    async def test_start_new_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
    ) -> None:
        kube_client.get_platform_status.return_value = None

        await manager.start_deployment("neuro")

        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload={"phase": "Deploying", "retries": 0},
        )

    async def test_start_existing_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment("neuro", retry=1)

        status["retries"] = 1
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload=status,
        )

    async def test_complete_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment("neuro", retry=1)

        status["retries"] = 1
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload=status,
        )

        await manager.complete_deployment("neuro")

        status["phase"] = "Deployed"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload=status,
        )

    async def test_fail_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.fail_deployment("neuro")

        status["phase"] = "Failed"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload=status,
        )

    async def test_start_deletion(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: dict[str, Any],
    ) -> None:
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deletion("neuro")

        status["phase"] = "Deleting"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload=status,
        )
