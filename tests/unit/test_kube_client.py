from copy import deepcopy
from typing import Any, Dict
from unittest import mock

import pytest

from platform_operator.kube_client import (
    KubeClient,
    PlatformConditionType,
    PlatformStatusManager,
)


class TestPlatformStatusManager:
    @pytest.fixture
    def kube_client(self) -> mock.AsyncMock:
        return mock.AsyncMock(KubeClient)

    @pytest.fixture
    def manager(self, kube_client: KubeClient) -> PlatformStatusManager:
        return PlatformStatusManager(kube_client, namespace="default", name="neuro")

    @pytest.fixture
    def status(self) -> Dict[str, Any]:
        return {
            "phase": "Deployed",
            "retries": 0,
            "conditions": [
                {
                    "type": "PlatformDeployed",
                    "status": "True",
                    "lastTransitionTime": "2020-05-24T22:13:39",
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_is_condition_satisfied(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment(retry=1)

        assert (
            manager.is_condition_satisfied(PlatformConditionType.PLATFORM_DEPLOYED)
            is True
        )
        assert (
            manager.is_condition_satisfied(PlatformConditionType.CLUSTER_CONFIGURED)
            is False
        )

    @pytest.mark.asyncio
    async def test_start_deployment_of_new_platform(
        self, kube_client: mock.AsyncMock, manager: PlatformStatusManager,
    ) -> None:
        kube_client.get_platform_status.return_value = None

        await manager.start_deployment(retry=0)

        kube_client.update_platform_status.assert_awaited_with(
            namespace="default",
            name="neuro",
            payload={"phase": "Deploying", "retries": 0, "conditions": []},
        )

    @pytest.mark.asyncio
    async def test_start_deployment_of_existing_platform(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["retries"] = 1
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment(retry=0)

        status["phase"] = "Deploying"
        status["retries"] = 0
        status["conditions"] = []
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_start_deployment_with_retry(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment(retry=1)

        status["retries"] = 1
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_transition(
        self, kube_client: mock.AsyncMock, manager: PlatformStatusManager,
    ) -> None:
        kube_client.get_platform_status.return_value = None

        await manager.start_deployment(retry=0)

        status: Dict[str, Any] = {"phase": "Deploying", "retries": 0, "conditions": []}
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

        async with manager.transition(PlatformConditionType.PLATFORM_DEPLOYED):
            status["conditions"].append(
                {
                    "type": "PlatformDeployed",
                    "status": "False",
                    "lastTransitionTime": mock.ANY,
                }
            )
            kube_client.update_platform_status.assert_awaited_with(
                namespace="default", name="neuro", payload=status,
            )

        status["conditions"][-1]["status"] = "True"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_complete_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deployment(retry=1)

        status["retries"] = 1
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

        await manager.complete_deployment()

        status["phase"] = "Deployed"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_fail_deployment(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.fail_deployment()

        status["phase"] = "Failed"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_fail_deployment_and_last_condition(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        status["phase"] = "Deploying"
        status["conditions"][-1]["status"] = "False"
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.fail_deployment()

        status["phase"] = "Failed"
        status["conditions"][-1]["status"] = "Unknown"
        status["conditions"][-1]["lastTransitionTime"] = mock.ANY
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )

    @pytest.mark.asyncio
    async def test_start_deletion(
        self,
        kube_client: mock.AsyncMock,
        manager: PlatformStatusManager,
        status: Dict[str, Any],
    ) -> None:
        kube_client.get_platform_status.return_value = deepcopy(status)

        await manager.start_deletion()

        status["phase"] = "Deleting"
        kube_client.update_platform_status.assert_awaited_with(
            namespace="default", name="neuro", payload=status,
        )
