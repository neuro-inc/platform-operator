import asyncio

import aiohttp
import pytest

from platform_operator.kube_client import KubeClient


class TestKubeClient:
    @pytest.mark.asyncio
    async def test_get_service(self, kube_client: KubeClient) -> None:
        service = await kube_client.get_service(namespace="default", name="kubernetes")

        assert service["metadata"]["name"] == "kubernetes"

    @pytest.mark.asyncio
    async def test_get_unknown_service__raises_error(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(aiohttp.ClientError):
            await kube_client.get_service(namespace="default", name="unknown")

    @pytest.mark.asyncio
    async def test_get_service_account_and_secret(
        self, kube_client: KubeClient
    ) -> None:
        service_account = await kube_client.get_service_account("default", "default")

        assert service_account["metadata"]["name"] == "default"

        secret_name = service_account["secrets"][0]["name"]
        secret = await kube_client.get_secret(namespace="default", name=secret_name)

        assert secret["metadata"]["name"] == secret_name
        assert secret["data"]["namespace"] == "default"

    @pytest.mark.asyncio
    async def test_get_unknown_secret__raises_error(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(aiohttp.ClientError):
            await kube_client.get_secret(namespace="default", name="unknown")

    @pytest.mark.asyncio
    async def test_get_pods(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="kube-system")

        assert len(result) > 1

    @pytest.mark.asyncio
    async def test_get_pods_with_limit(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="kube-system", limit=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_pods_with_label_selector(self, kube_client: KubeClient) -> None:
        pods = await kube_client.get_pods(
            namespace="kube-system", label_selector={"k8s-app": "kube-proxy"}
        )

        for pod in pods:
            assert pod["metadata"]["name"].startswith("kube-proxy")

    @pytest.mark.asyncio
    async def test_get_pods_in_unknown_namespace(self, kube_client: KubeClient) -> None:
        result = await kube_client.get_pods(namespace="unknown")

        assert result == []

    @pytest.mark.asyncio
    async def test_wait_till_pods_deleted(
        self, kube_client: KubeClient, kube_namespace: str
    ) -> None:
        await kube_client.wait_till_pods_deleted(namespace=kube_namespace)

    @pytest.mark.asyncio
    async def test_wait_till_pods_deleted_forever(
        self, kube_client: KubeClient
    ) -> None:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                kube_client.wait_till_pods_deleted(
                    namespace="kube-system", interval_secs=1
                ),
                2,
            )
