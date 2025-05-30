from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import aiobotocore.session
import pytest

from platform_operator.aws_client import AwsElbClient


class TestAwsElbClient:
    @pytest.fixture
    async def load_balancer(
        self, elb_client: AwsElbClient, ec2_client: aiobotocore.session.AioBaseClient
    ) -> AsyncIterator[dict[str, Any]]:
        response = await ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
        response = await ec2_client.create_subnet(
            VpcId=response["Vpc"]["VpcId"], CidrBlock="10.0.0.0/24"
        )
        name = str(uuid.uuid4())
        response = await elb_client.create_load_balancer(
            Name=name,
            Type="network",
            Scheme="internet-facing",
            Subnets=[response["Subnet"]["SubnetId"]],
        )
        load_balancer = response["LoadBalancers"][0]
        yield {
            "LoadBalancerName": name,
            "DNSName": load_balancer["DNSName"],  # type: ignore
        }
        await elb_client.delete_load_balancer(
            LoadBalancerArn=load_balancer["LoadBalancerArn"]  # type: ignore
        )

    async def test_get_load_balancer_by_dns_name(
        self, load_balancer: dict[str, Any], elb_client: AwsElbClient
    ) -> None:
        result = await elb_client.get_load_balancer_by_dns_name(
            load_balancer["DNSName"]
        )

        assert result
        assert result["LoadBalancerName"] == load_balancer["LoadBalancerName"]
