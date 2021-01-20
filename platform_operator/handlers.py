import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from logging import Logger
from typing import Any, Dict, Optional

import kopf
from kopf.structs import bodies

from .aws_client import AwsElbClient
from .certificate_store import CertificateStore
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
    certificate_store: CertificateStore = None  # type: ignore
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
        ConfigClient(config.platform_config_url)
    )
    app.certificate_store = await app.exit_stack.enter_async_context(
        CertificateStore(config.platform_consul_url)
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
    PLATFORM_GROUP,
    PLATFORM_API_VERSION,
    PLATFORM_PLURAL,
    backoff=config.backoff,
)
async def deploy(
    name: str,
    body: bodies.Body,
    logger: Logger,
    retry: int,
    **kwargs: Any,
) -> None:
    status_manager = PlatformStatusManager(
        app.kube_client,
        namespace=config.platform_namespace,
        name=name,
        logger=logger,
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
            await app.kube_client.update_service_account_image_pull_secrets(
                namespace=platform.namespace,
                name=platform.service_account_name,
                image_pull_secrets=platform.image_pull_secret_names,
            )
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

    if (
        platform.ingress_controller_enabled
        and not status_manager.is_condition_satisfied(
            PlatformConditionType.CERTIFICATE_CREATED
        )
    ):
        async with status_manager.transition(PlatformConditionType.CERTIFICATE_CREATED):
            await asyncio.wait_for(
                app.certificate_store.wait_till_certificate_created(), 300
            )

    if not status_manager.is_condition_satisfied(
        PlatformConditionType.CLUSTER_CONFIGURED
    ):
        async with status_manager.transition(PlatformConditionType.CLUSTER_CONFIGURED):
            await configure_cluster(platform)

    await status_manager.complete_deployment()
    logger.info("Platform deployment succeeded")


@kopf.on.delete(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def delete(
    name: str,
    body: bodies.Body,
    logger: Logger,
    retry: int,
    **_: Any,
) -> None:
    status_manager = PlatformStatusManager(
        app.kube_client,
        namespace=config.platform_namespace,
        name=name,
    )
    if retry == 0:
        await status_manager.start_deletion()

    platform_token = body["spec"]["token"]
    cluster = await app.config_client.get_cluster(name, platform_token)

    try:
        platform = app.platform_config_factory.create(body, cluster)
    except Exception:
        # If platform has invalid configuration than there was no deployment
        # and no resources to delete. Platform resource can be safely deleted.
        logger.warning(
            "Platform has invalid configuration, delete handler cannot proceed"
        )
        return

    await app.helm_client.init(client_only=True, skip_refresh=True)

    logger.info("Deleting platform helm chart")
    await app.helm_client.delete(
        config.helm_release_names.platform,
        purge=True,
    )
    logger.info("platform helm chart deleted")

    try:
        # We need first to delete all pods that use storage.
        # Otherwise they can stuck in Termnating state because kubernetes
        # will fail to unmount volumes from pods.
        logger.info("Waiting for job pods to be deleted")
        await asyncio.wait_for(
            app.kube_client.wait_till_pods_deleted(namespace=platform.jobs_namespace),
            600,
        )
        logger.info("Job pods deleted")

        logger.info("Waiting for platform storage pods to be deleted")
        await asyncio.wait_for(
            app.kube_client.wait_till_pods_deleted(
                namespace=platform.namespace,
                label_selector={"service": "platformstorageapi"},
            ),
            600,
        )
        logger.info("Platform storage pods deleted")
    except asyncio.TimeoutError:
        message = "Timeout error while wating for pods to be deleted"
        logger.error(message)
        raise kopf.TemporaryError(message)

    is_gcp_gcs_platform = platform.gcp and platform.gcp.storage_type == "gcs"
    if is_gcp_gcs_platform:
        logger.info("Deleting obs-csi-driver helm chart")
        await app.helm_client.delete(
            config.helm_release_names.obs_csi_driver,
            purge=True,
        )
        logger.info("obs-csi-driver helm chart deleted")

    if platform.on_prem:
        logger.info("Deleting nfs-server helm chart")
        await app.helm_client.delete(
            config.helm_release_names.nfs_server,
            purge=True,
        )
        logger.info("nfs-server helm chart deleted")


async def configure_cluster(platform: PlatformConfig) -> None:
    traefik_service: Optional[Dict[str, Any]] = None
    aws_traefik_lb: Optional[Dict[str, Any]] = None

    if platform.ingress_controller_enabled:
        traefik_service = await app.kube_client.get_service(
            namespace=platform.namespace, name=platform.service_traefik_name
        )
        if platform.aws:
            async with AwsElbClient(region=platform.aws.region) as client:
                aws_traefik_lb = await client.get_load_balancer_by_dns_name(
                    traefik_service["status"]["loadBalancer"]["ingress"][0]["hostname"]
                )

    service_account = await app.kube_client.get_service_account(
        namespace=platform.jobs_namespace,
        name=platform.jobs_service_account_name,
    )
    secret_name = service_account["secrets"][0]["name"]
    secret = await app.kube_client.get_secret(
        namespace=platform.jobs_namespace,
        name=secret_name,
    )
    cluster_config = platform.create_cluster_config(
        service_account_secret=secret,
        traefik_service=traefik_service,
        aws_traefik_lb=aws_traefik_lb,
    )
    await app.config_client.patch_cluster(
        cluster_name=platform.cluster_name, token=platform.token, payload=cluster_config
    )
