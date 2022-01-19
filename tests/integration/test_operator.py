from platform_operator.consul_client import ConsulClient
from platform_operator.operator import (
    end_operator_deployment,
    start_operator_deployment,
)


class TestOperatorDeployment:
    async def test_on_install(self, consul_client: ConsulClient) -> None:
        await start_operator_deployment(consul_client, 1)
        await end_operator_deployment(consul_client, 1)

    async def test_on_upgrade(self, consul_client: ConsulClient) -> None:
        await start_operator_deployment(consul_client, 2)
        await end_operator_deployment(consul_client, 2)
