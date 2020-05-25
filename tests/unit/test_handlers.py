from typing import Any, Dict, Iterator
from unittest import mock

import pytest

from platform_operator.aws_client import AwsElbClient
from platform_operator.config_client import ConfigClient
from platform_operator.kube_client import KubeClient
from platform_operator.models import Config, PlatformConfig


@pytest.fixture
def setup_config(config: Config) -> Iterator[None]:
    with mock.patch.object(Config, "load_from_env") as method:
        method.return_value = config
        yield


@pytest.fixture
def kube_client() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.kube_client", spec=KubeClient
    ) as client:
        yield client


@pytest.fixture
def config_client() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.config_client", spec=ConfigClient
    ) as client:
        yield client


@pytest.fixture
def aws_elb_client() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.AwsElbClient", spec=AwsElbClient
    ) as client_class:
        client_instance = mock.AsyncMock(AwsElbClient)
        client_instance.__aenter__.return_value = client_instance
        client_class.return_value = client_instance
        yield client_instance


@pytest.fixture
def traefik_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
    }


@pytest.fixture
def ssh_auth_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.2"}]}},
    }


@pytest.fixture
def aws_traefik_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"hostname": "platform-traefik"}]}},
    }


@pytest.fixture
def aws_ssh_auth_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"hostname": "ssh-auth"}]}},
    }


@pytest.fixture
def aws_traefik_lb() -> Dict[str, Any]:
    return {
        "CanonicalHostedZoneNameID": "/hostedzone/traefik",
    }


@pytest.fixture
def aws_ssh_auth_lb() -> Dict[str, Any]:
    return {
        "CanonicalHostedZoneNameID": "/hostedzone/ssh-auth",
    }


@pytest.fixture
def service_account() -> Dict[str, Any]:
    return {"secrets": [{"name": "token"}]}


@pytest.fixture
def service_account_secret() -> Dict[str, Any]:
    return {"data": {"ca.crt": "cert-authority-data", "token": "token"}}


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_config")
async def test_configure_dns(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    gcp_platform_config: PlatformConfig,
    traefik_service: Dict[str, Any],
    ssh_auth_service: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_dns

    kube_client.get_service.side_effect = [traefik_service, ssh_auth_service]

    await configure_dns(gcp_platform_config)

    kube_client.get_service.assert_has_awaits(
        [
            mock.call(namespace="platform", name="platform-traefik"),
            mock.call(namespace="platform", name="ssh-auth"),
        ]
    )
    config_client.configure_dns.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_dns_config(
            traefik_service=traefik_service, ssh_auth_service=ssh_auth_service
        ),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_config")
async def test_configure_aws_dns(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    aws_elb_client: mock.Mock,
    aws_platform_config: PlatformConfig,
    aws_traefik_service: Dict[str, Any],
    aws_ssh_auth_service: Dict[str, Any],
    aws_traefik_lb: Dict[str, Any],
    aws_ssh_auth_lb: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_dns

    kube_client.get_service.side_effect = [aws_traefik_service, aws_ssh_auth_service]
    aws_elb_client.get_load_balancer_by_dns_name.side_effect = [
        aws_traefik_lb,
        aws_ssh_auth_lb,
    ]

    await configure_dns(aws_platform_config)

    kube_client.get_service.assert_has_awaits(
        [
            mock.call(namespace="platform", name="platform-traefik"),
            mock.call(namespace="platform", name="ssh-auth"),
        ]
    )
    aws_elb_client.get_load_balancer_by_dns_name.assert_has_awaits(
        [mock.call("platform-traefik"), mock.call("ssh-auth")]
    )
    config_client.configure_dns.assert_awaited_with(
        cluster_name=aws_platform_config.cluster_name,
        token=aws_platform_config.token,
        payload=aws_platform_config.create_dns_config(
            traefik_service=aws_traefik_service,
            ssh_auth_service=aws_ssh_auth_service,
            aws_traefik_lb=aws_traefik_lb,
            aws_ssh_auth_lb=aws_ssh_auth_lb,
        ),
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("setup_config")
async def test_configure_cluster(
    gcp_platform_config: PlatformConfig,
    kube_client: mock.Mock,
    config_client: mock.Mock,
    service_account: Dict[str, Any],
    service_account_secret: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster

    kube_client.get_service_account.return_value = service_account
    kube_client.get_secret.return_value = service_account_secret

    await configure_cluster(gcp_platform_config)

    kube_client.get_service_account.assert_awaited_with(
        namespace="platform-jobs", name="platform-jobs",
    )
    kube_client.get_secret.assert_awaited_with(namespace="platform-jobs", name="token")
    config_client.configure_cluster.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_cluster_config(service_account_secret),
    )
