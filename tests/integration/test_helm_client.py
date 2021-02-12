import uuid
from typing import Any, Dict

import pytest
from yarl import URL

from platform_operator.helm_client import HelmClient, HelmException
from platform_operator.models import HelmRepo


@pytest.fixture
def config_map() -> Dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "test"},
        "data": {"hello": "world"},
    }


class TestHelmClient:
    @pytest.mark.asyncio
    async def test_upgrade_and_delete(
        self,
        kube_namespace: str,
        helm_client: HelmClient,
        config_map: Dict[str, Any],
    ) -> None:
        await helm_client.init(client_only=True)
        await helm_client.add_repo(
            HelmRepo("incubator", URL("https://charts.helm.sh/incubator"))
        )
        await helm_client.update_repo()
        release_name = str(uuid.uuid4())
        try:
            await helm_client.upgrade(
                release_name,
                "incubator/raw",
                values={"resources": [config_map]},
                version="0.2.3",
                namespace=kube_namespace,
                install=True,
                wait=True,
            )
            release = await helm_client.get_release(release_name)

            assert release
            assert release["Name"] == release_name
            assert release["Chart"] == "raw-0.2.3"
            assert release["Namespace"] == kube_namespace
            assert release["Status"] == "DEPLOYED"
        finally:
            await helm_client.delete(release_name, purge=True)

    @pytest.mark.asyncio
    async def test_add_unknown_repo(self, helm_client: HelmClient) -> None:
        with pytest.raises(
            HelmException,
            match="Failed to add helm repo unknown https://unknown",
        ):
            await helm_client.init(client_only=True)
            await helm_client.add_repo(HelmRepo("unknown", URL("https://unknown")))

    @pytest.mark.asyncio
    async def test_install_unknown_chart(self, helm_client: HelmClient) -> None:
        with pytest.raises(
            HelmException,
            match="Failed to upgrade release unknown",
        ):
            await helm_client.init(client_only=True)
            await helm_client.upgrade(
                "unknown",
                "unknown/unknown",
                install=True,
                wait=True,
            )

    @pytest.mark.asyncio
    async def test_delete_unknown_release(self, helm_client: HelmClient) -> None:
        await helm_client.init(client_only=True)
        await helm_client.delete("unknown", purge=True)
