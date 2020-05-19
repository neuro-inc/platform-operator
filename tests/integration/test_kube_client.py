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
