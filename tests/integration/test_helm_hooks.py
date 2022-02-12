from platform_operator.helm_hooks import (
    end_helm_chart_upgrade,
    start_helm_chart_upgrade,
)
from platform_operator.kube_client import KubeClient


class TestOperatorDeployment:
    async def test_on_upgrade(self, kube_client: KubeClient) -> None:
        await start_helm_chart_upgrade(kube_client, "kube-system", "coredns")
        await end_helm_chart_upgrade(kube_client, "kube-system", "coredns")

    async def test_on_upgrade_deployment_not_found(
        self, kube_client: KubeClient
    ) -> None:
        await start_helm_chart_upgrade(kube_client, "kube-system", "unknown")
        await end_helm_chart_upgrade(kube_client, "kube-system", "unknown")
