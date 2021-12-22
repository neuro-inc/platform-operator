from __future__ import annotations

import uuid
from typing import Any

import pytest
from yarl import URL

from platform_operator.helm_client import HelmClient, HelmException, ReleaseStatus
from platform_operator.models import HelmRepo


@pytest.fixture
def config_map() -> dict[str, Any]:
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
        config_map: dict[str, Any],
    ) -> None:
        await helm_client.add_repo(
            HelmRepo(URL("https://charts.helm.sh/incubator"), name="incubator")
        )
        await helm_client.update_repo()
        release_name = str(uuid.uuid4())
        values = {"resources": [config_map]}
        try:
            await helm_client.upgrade(
                release_name,
                "incubator/raw",
                values=values,
                version="0.2.3",
                install=True,
                wait=True,
            )
            release = await helm_client.get_release(release_name)

            assert release
            assert release.name == release_name
            assert release.chart == "raw-0.2.3"
            assert release.namespace == kube_namespace
            assert release.status == ReleaseStatus.DEPLOYED

            release_values = await helm_client.get_release_values(release_name)

            assert release_values
            assert release_values == values
        finally:
            await helm_client.delete(release_name)

    @pytest.mark.asyncio
    async def test_add_unknown_repo(self, helm_client: HelmClient) -> None:
        with pytest.raises(
            HelmException,
            match="Failed to add helm repo unknown https://unknown",
        ):
            await helm_client.add_repo(HelmRepo(URL("https://unknown"), name="unknown"))

    @pytest.mark.asyncio
    async def test_install_unknown_chart(self, helm_client: HelmClient) -> None:
        with pytest.raises(
            HelmException,
            match="Failed to upgrade release unknown",
        ):
            await helm_client.upgrade(
                "unknown",
                "unknown/unknown",
                install=True,
                wait=True,
            )

    @pytest.mark.asyncio
    async def test_delete_unknown_release(self, helm_client: HelmClient) -> None:
        await helm_client.delete("unknown")
