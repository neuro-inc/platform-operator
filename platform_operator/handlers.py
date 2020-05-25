import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import kopf

from .aws_client import AwsElbClient
from .config_client import ConfigClient
from .helm_client import HelmClient
from .helm_values import HelmValuesFactory
from .kube_client import KubeClient
from .models import Config, PlatformConfig, PlatformConfigFactory


@dataclass
class App:
    platform_config_factory: PlatformConfigFactory = None  # type: ignore
    helm_values_factory: HelmValuesFactory = None  # type: ignore
    helm_client: HelmClient = None  # type: ignore
    kube_client: KubeClient = None  # type: ignore
    config_client: ConfigClient = None  # type: ignore
    exit_stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def close(self) -> None:
        await self.exit_stack.aclose()


config = Config.load_from_env()
app = App()


@kopf.on.startup()
async def startup(settings: kopf.OperatorSettings, **_: Any) -> None:
    app.helm_values_factory = HelmValuesFactory(
        config.helm_release_names, config.helm_chart_names
    )
    app.platform_config_factory = PlatformConfigFactory(config)
    app.helm_client = HelmClient(tiller_namespace=config.platform_namespace)
    app.kube_client = await app.exit_stack.enter_async_context(
        KubeClient(config.kube_config)
    )
    app.config_client = await app.exit_stack.enter_async_context(
        ConfigClient(config.platform_url)
    )

    settings.posting.level = logging.getLevelName(config.log_level)
    settings.persistence.progress_storage = (
        kopf.storage.progress.AnnotationsProgressStorage()
    )
    settings.persistence.diffbase_storage = (
        kopf.storage.diffbase.AnnotationsDiffBaseStorage()
    )


@kopf.on.cleanup()
async def cleanup(**_: Any) -> None:
    await app.close()


async def configure_dns(platform: PlatformConfig) -> None:
    traefik_service = await app.kube_client.get_service(
        namespace=platform.namespace, name=platform.service_traefik_name
    )
    ssh_auth_service = await app.kube_client.get_service(
        namespace=platform.namespace, name=platform.service_ssh_auth_name
    )
    aws_traefik_lb: Optional[Dict[str, Any]] = None
    aws_ssh_auth_lb: Optional[Dict[str, Any]] = None
    if platform.aws:
        print(AwsElbClient)
        async with AwsElbClient(region=platform.aws.region) as client:
            aws_traefik_lb = await client.get_load_balancer_by_dns_name(
                traefik_service["status"]["loadBalancer"]["ingress"][0]["hostname"]
            )
            aws_ssh_auth_lb = await client.get_load_balancer_by_dns_name(
                ssh_auth_service["status"]["loadBalancer"]["ingress"][0]["hostname"]
            )
    dns_config = platform.create_dns_config(
        traefik_service=traefik_service,
        ssh_auth_service=ssh_auth_service,
        aws_traefik_lb=aws_traefik_lb,
        aws_ssh_auth_lb=aws_ssh_auth_lb,
    )
    await app.config_client.configure_dns(
        cluster_name=platform.cluster_name, token=platform.token, payload=dns_config
    )


async def configure_cluster(platform: PlatformConfig) -> None:
    service_account = await app.kube_client.get_service_account(
        namespace=platform.jobs_namespace, name=platform.jobs_service_account_name,
    )
    secret_name = service_account["secrets"][0]["name"]
    secret = await app.kube_client.get_secret(
        namespace=platform.jobs_namespace, name=secret_name,
    )
    cluster_config = platform.create_cluster_config(secret)
    await app.config_client.configure_cluster(
        cluster_name=platform.cluster_name, token=platform.token, payload=cluster_config
    )
