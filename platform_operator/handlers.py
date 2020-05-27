import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from logging import Logger
from typing import Any, Dict, Optional

import kopf
from kopf.structs import bodies

from .aws_client import AwsElbClient
from .config_client import ConfigClient
from .helm_client import HelmClient
from .helm_values import HelmValuesFactory
from .kube_client import (
    PLATFORM_API_VERSION,
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    KubeClient,
    PlatformConditionType,
    PlatformStatusManager,
)
from .models import Config, HelmRepoName, PlatformConfig, PlatformConfigFactory


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


@kopf.on.create(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
@kopf.on.update(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff,
)
async def deploy(
    name: str, body: bodies.Body, logger: Logger, retry: int, **kwargs: Any,
) -> None:
    status_manager = PlatformStatusManager(
        app.kube_client, namespace=config.platform_namespace, name=name, logger=logger,
    )
    if retry > config.retries:
        await status_manager.fail_deployment()
        raise kopf.HandlerRetriesError(
            f"Platform deployment has exceeded {config.retries} retries"
        )
    else:
        await status_manager.start_deployment(retry)

    platform_token = body["spec"]["token"]
    cluster = await app.config_client.get_cluster(
        cluster_name=name, token=platform_token
    )

    try:
        platform = app.platform_config_factory.create(body, cluster)
    except Exception as ex:
        await status_manager.fail_deployment()
        raise kopf.PermanentError(f"Invalid platform configuration: {ex!s}")

    logger.info("Platform deployment started")

    await app.helm_client.init(client_only=True, skip_refresh=True)
    await app.helm_client.add_repo(config.helm_stable_repo)
    await app.helm_client.add_repo(platform.helm_repo)
    await app.helm_client.update_repo()

    is_gcp_gcs_platform = platform.gcp and platform.gcp.storage_type == "gcs"
    if is_gcp_gcs_platform and not status_manager.is_condition_satisfied(
        PlatformConditionType.OBS_CSI_DRIVER_DEPLOYED
    ):
        async with status_manager.transition(
            PlatformConditionType.OBS_CSI_DRIVER_DEPLOYED
        ):
            await app.helm_client.upgrade(
                config.helm_release_names.obs_csi_driver,
                f"{HelmRepoName.NEURO}/{config.helm_chart_names.obs_csi_driver}",
                values=app.helm_values_factory.create_obs_csi_driver_values(platform),
                version=config.helm_chart_versions.obs_csi_driver,
                namespace=config.platform_namespace,
                install=True,
                wait=True,
                timeout=600,
            )

    if platform.on_prem and not status_manager.is_condition_satisfied(
        PlatformConditionType.NFS_SERVER_DEPLOYED
    ):
        async with status_manager.transition(PlatformConditionType.NFS_SERVER_DEPLOYED):
            await app.helm_client.upgrade(
                config.helm_release_names.nfs_server,
                f"{HelmRepoName.NEURO}/{config.helm_chart_names.nfs_server}",
                values=app.helm_values_factory.create_nfs_server_values(platform),
                version=config.helm_chart_versions.nfs_server,
                namespace=config.platform_namespace,
                install=True,
                wait=True,
                timeout=600,
            )

    if not status_manager.is_condition_satisfied(
        PlatformConditionType.PLATFORM_DEPLOYED
    ):
        async with status_manager.transition(PlatformConditionType.PLATFORM_DEPLOYED):
            await app.helm_client.upgrade(
                config.helm_release_names.platform,
                f"{HelmRepoName.NEURO}/{config.helm_chart_names.platform}",
                values=app.helm_values_factory.create_platform_values(platform),
                version=config.helm_chart_versions.platform,
                namespace=config.platform_namespace,
                install=True,
                wait=True,
                timeout=600,
            )

    if not status_manager.is_condition_satisfied(
        PlatformConditionType.SSL_CERT_CREATED
    ):
        async with status_manager.transition(PlatformConditionType.SSL_CERT_CREATED):
            await wait_till_ssl_cert_created()

    if not status_manager.is_condition_satisfied(PlatformConditionType.DNS_CONFIGURED):
        async with status_manager.transition(PlatformConditionType.DNS_CONFIGURED):
            await configure_dns(platform)

    if not status_manager.is_condition_satisfied(
        PlatformConditionType.CLUSTER_CONFIGURED
    ):
        async with status_manager.transition(PlatformConditionType.CLUSTER_CONFIGURED):
            await configure_cluster(platform)

    await status_manager.complete_deployment()
    logger.info("Platform deployment succeeded")


async def wait_till_ssl_cert_created() -> None:
    # TODO: implement something smarter than just delay
    await asyncio.sleep(300)


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
