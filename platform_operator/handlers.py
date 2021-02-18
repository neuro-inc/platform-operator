import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from logging import Logger
from typing import Any, Dict, Optional

import kopf
from kopf.structs import bodies, primitives

from platform_operator.consul_client import ConsulClient

from .aws_client import AwsElbClient
from .certificate_store import CertificateStore
from .config_client import ConfigClient, NotificationType
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
from .operator import LOCK_KEY


@dataclass
class App:
    platform_config_factory: PlatformConfigFactory = None  # type: ignore
    helm_values_factory: HelmValuesFactory = None  # type: ignore
    helm_client: HelmClient = None  # type: ignore
    kube_client: KubeClient = None  # type: ignore
    status_manager: PlatformStatusManager = None  # type: ignore
    consul_client: ConsulClient = None  # type: ignore
    config_client: ConfigClient = None  # type: ignore
    certificate_store: CertificateStore = None  # type: ignore
    exit_stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def close(self) -> None:
        await self.exit_stack.aclose()


config = Config.load_from_env()
app = App()


@kopf.on.startup()
async def startup(settings: kopf.OperatorSettings, **kwargs: Any) -> None:
    app.helm_values_factory = HelmValuesFactory(
        config.helm_release_names, config.helm_chart_names
    )
    app.platform_config_factory = PlatformConfigFactory(config)
    app.helm_client = HelmClient(tiller_namespace=config.platform_namespace)
    app.kube_client = await app.exit_stack.enter_async_context(
        KubeClient(config.kube_config)
    )
    app.status_manager = PlatformStatusManager(
        app.kube_client, namespace=config.platform_namespace
    )
    app.config_client = await app.exit_stack.enter_async_context(
        ConfigClient(config.platform_config_url)
    )
    app.consul_client = await app.exit_stack.enter_async_context(
        ConsulClient(config.consul_url)
    )
    app.certificate_store = CertificateStore(app.consul_client)

    settings.posting.level = logging.getLevelName(config.log_level)
    settings.persistence.progress_storage = (
        kopf.storage.progress.AnnotationsProgressStorage()
    )
    settings.persistence.diffbase_storage = (
        kopf.storage.diffbase.AnnotationsDiffBaseStorage()
    )

    # https://github.com/nolar/kopf/issues/232
    settings.watching.server_timeout = 5 * 60
    settings.watching.client_timeout = 5 * 60
    settings.watching.connect_timeout = 30
    settings.watching.reconnect_backoff = 1


@kopf.on.cleanup()
async def cleanup(**kwargs: Any) -> None:
    await app.close()


@kopf.on.login()
def login(**kwargs: Any) -> kopf.ConnectionInfo:
    ca_path = None
    if config.kube_config.cert_authority_path:
        ca_path = str(config.kube_config.cert_authority_path)

    ca_data = None
    if config.kube_config.cert_authority_data_pem:
        ca_data = config.kube_config.cert_authority_data_pem.encode()

    token = None
    if config.kube_config.auth_token:
        token = config.kube_config.auth_token
    if config.kube_config.auth_token_path:
        token = config.kube_config.auth_token_path.read_text()

    return kopf.ConnectionInfo(
        server=str(config.kube_config.url),
        scheme="Bearer",
        token=token,
        ca_path=ca_path,
        ca_data=ca_data,
        default_namespace=config.platform_namespace,
    )


@kopf.on.create(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
@kopf.on.update(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def deploy(
    name: str, body: bodies.Body, logger: Logger, retry: int, **kwargs: Any
) -> None:
    if retry > config.retries:
        await app.status_manager.fail_deployment(name)
        raise kopf.HandlerRetriesError(
            f"Platform deployment has exceeded {config.retries} retries"
        )

    await app.consul_client.wait_healthy(sleep_s=0.5)

    async with app.consul_client.lock_key(
        LOCK_KEY,
        b"platform-deploying",
        session_ttl_s=15 * 60,
        sleep_s=3,
    ):
        await _deploy(name, body, logger, retry)


async def _deploy(name: str, body: bodies.Body, logger: Logger, retry: int) -> None:
    platform = await get_platform_config(name, body)

    logger.info("Platform deployment started")

    await app.status_manager.start_deployment(name, retry)
    await initialize_helm(platform)

    if await is_obs_csi_driver_deploy_required(platform, install=True):
        await upgrade_obs_csi_driver_helm_release(platform)

    if await is_platform_deploy_required(platform, install=True):
        await upgrade_platform_helm_release(platform)

    await wait_for_certificated_created(platform)
    await wait_for_cluster_configured(platform)
    await app.status_manager.complete_deployment(name)

    logger.info("Platform deployment succeeded")


@kopf.on.delete(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def delete(
    name: str, body: bodies.Body, logger: Logger, retry: int, **kwargs: Any
) -> None:
    if retry == 0:
        await app.status_manager.start_deletion(name)

    async with app.consul_client.lock_key(
        LOCK_KEY,
        b"platform-deploying",
        session_ttl_s=15 * 60,
        sleep_s=3,
    ):
        await _delete(name, body, logger)


async def _delete(name: str, body: bodies.Body, logger: Logger) -> None:
    try:
        platform = await get_platform_config(name, body)
    except Exception:
        # If platform has invalid configuration than there was no deployment
        # and no resources to delete. Platform resource can be safely deleted.
        logger.warning(
            "Platform has invalid configuration, delete handler cannot proceed"
        )
        return

    await app.helm_client.init(client_only=True, skip_refresh=True)

    await app.helm_client.delete(
        config.helm_release_names.platform,
        purge=True,
    )

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
        await app.helm_client.delete(
            config.helm_release_names.obs_csi_driver,
            purge=True,
        )


@kopf.on.daemon(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def watch_config(
    name: str,
    body: bodies.Body,
    logger: Logger,
    stopped: primitives.AsyncDaemonStopperChecker,
    **kwargs: Any,
) -> None:
    await app.consul_client.wait_healthy(sleep_s=0.5)

    while True:
        if stopped:
            break

        logger.info(
            "Platform config will be checked in %d seconds",
            config.platform_config_watch_interval_s,
        )
        await asyncio.sleep(config.platform_config_watch_interval_s)

        try:
            async with app.consul_client.lock_key(
                LOCK_KEY,
                b"platform-config-updating",
                session_ttl_s=15 * 60,
                sleep_s=3,
            ):
                await _update(name, body, logger)
        except Exception as exc:
            logger.error("Platform config update failed", exc_info=exc)
            await app.status_manager.fail_deployment(name)
            await app.config_client.send_notification(
                cluster_name=name,
                token=body["spec"]["token"],
                notification_type=NotificationType.CLUSTER_UPDATE_FAILED,
            )


async def _update(name: str, body: bodies.Body, logger: Logger) -> None:
    platform = await get_platform_config(name, body)

    await initialize_helm(platform)

    obs_csi_driver_deploy_required = await is_obs_csi_driver_deploy_required(platform)
    platform_deploy_required = await is_platform_deploy_required(platform)

    if not obs_csi_driver_deploy_required and not platform_deploy_required:
        logger.info("Platform config didn't change")
        return

    logger.info("Platform config update started")

    await app.status_manager.start_deployment(name)
    await app.config_client.send_notification(
        cluster_name=name,
        token=body["spec"]["token"],
        notification_type=NotificationType.CLUSTER_UPDATING,
    )

    if obs_csi_driver_deploy_required:
        await upgrade_obs_csi_driver_helm_release(platform)

    if platform_deploy_required:
        await upgrade_platform_helm_release(platform)

    await wait_for_certificated_created(platform)
    await wait_for_cluster_configured(platform)
    await app.status_manager.complete_deployment(name)
    await app.config_client.send_notification(
        cluster_name=name,
        token=body["spec"]["token"],
        notification_type=NotificationType.CLUSTER_UPDATE_SUCCEEDED,
    )

    logger.info("Platform config update succeeded")


async def get_platform_config(name: str, body: bodies.Body) -> PlatformConfig:
    token = body["spec"]["token"]
    cluster = await app.config_client.get_cluster(cluster_name=name, token=token)

    try:
        return app.platform_config_factory.create(body, cluster)
    except Exception as ex:
        await app.status_manager.fail_deployment(name, remove_conditions=True)
        raise kopf.PermanentError(f"Invalid platform configuration: {ex!s}")


async def is_obs_csi_driver_deploy_required(
    platform: PlatformConfig, install: bool = False
) -> bool:
    if not platform.gcp or platform.gcp.storage_type != "gcs":
        return False

    old_release = await app.helm_client.get_release(
        config.helm_release_names.obs_csi_driver
    )

    if not old_release:
        return install

    old_chart = old_release["Chart"]
    old_release_values = await app.helm_client.get_release_values(
        config.helm_release_names.obs_csi_driver
    )

    new_release_values = app.helm_values_factory.create_obs_csi_driver_values(platform)
    new_chart = (
        f"{config.helm_chart_names.obs_csi_driver}"
        f"-{config.helm_chart_versions.obs_csi_driver}"
    )

    return old_chart != new_chart or old_release_values != new_release_values


async def is_platform_deploy_required(
    platform: PlatformConfig, install: bool = False
) -> bool:
    old_release = await app.helm_client.get_release(config.helm_release_names.platform)

    if not old_release:
        return install

    old_chart = old_release["Chart"]
    old_release_values = await app.helm_client.get_release_values(
        config.helm_release_names.platform
    )

    new_release_values = app.helm_values_factory.create_platform_values(platform)
    new_chart = (
        f"{config.helm_chart_names.platform}-{config.helm_chart_versions.platform}"
    )

    return old_chart != new_chart or old_release_values != new_release_values


async def initialize_helm(platform: PlatformConfig) -> None:
    await app.helm_client.init(client_only=True, skip_refresh=True)
    await app.helm_client.add_repo(config.helm_stable_repo)
    await app.helm_client.add_repo(platform.helm_repo)
    await app.helm_client.update_repo()


async def upgrade_obs_csi_driver_helm_release(platform: PlatformConfig) -> None:
    if app.status_manager.is_condition_satisfied(
        platform.cluster_name, PlatformConditionType.OBS_CSI_DRIVER_DEPLOYED
    ):
        return

    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.OBS_CSI_DRIVER_DEPLOYED
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


async def upgrade_platform_helm_release(platform: PlatformConfig) -> None:
    if app.status_manager.is_condition_satisfied(
        platform.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    ):
        return

    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    ):
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


async def wait_for_certificated_created(platform: PlatformConfig) -> None:
    if (
        not platform.ingress_controller_enabled
        or app.status_manager.is_condition_satisfied(
            platform.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
        )
    ):
        return

    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    ):
        await asyncio.wait_for(
            app.certificate_store.wait_till_certificate_created(), 300
        )


async def wait_for_cluster_configured(platform: PlatformConfig) -> None:
    if app.status_manager.is_condition_satisfied(
        platform.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    ):
        return

    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    ):
        await configure_cluster(platform)


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
