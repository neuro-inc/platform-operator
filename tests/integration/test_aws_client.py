from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from platform_operator.aws_client import AwsElbClient


class TestAwsElbClient:
    @pytest.fixture
    async def load_balancer(
        self, elb_client: AwsElbClient
    ) -> AsyncIterator[dict[str, Any]]:
        name = str(uuid.uuid4())
        response = await elb_client.create_load_balancer(
            LoadBalancerName=name,
            Listeners=[
                {
                    "Protocol": "string",
                    "LoadBalancerPort": 123,
                    "InstanceProtocol": "string",
                    "InstancePort": 123,
                }
            ],
        )
        yield {"LoadBalancerName": name, "DNSName": response["DNSName"]}
        await elb_client.delete_load_balancer(LoadBalancerName=name)

    @pytest.mark.asyncio
    async def test_get_load_balancer_by_dns_name(
        self, load_balancer: dict[str, Any], elb_client: AwsElbClient
    ) -> None:
        result = await elb_client.get_load_balancer_by_dns_name(
            load_balancer["DNSName"]
        )

        assert result
        assert result["LoadBalancerName"] == load_balancer["LoadBalancerName"]
