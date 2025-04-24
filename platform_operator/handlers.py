from __future__ import annotations

import asyncio
import logging
import ssl
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from logging import Logger
from typing import Any

import aiohttp
import kopf
from neuro_config_client import (
    ACMEEnvironment,
    CloudProviderType,
    Cluster,
    ConfigClient,
    PatchClusterRequest,
)

from .aws_client import AwsElbClient, S3Client
from .helm_client import HelmClient, ReleaseStatus
from .helm_values import HelmValuesFactory
from .kube_client import (
    PLATFORM_API_VERSION,
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    KubeClient,
    PlatformConditionType,
    PlatformPhase,
    PlatformStatusManager,
)
from .models import BucketsProvider, Config, PlatformConfig, PlatformConfigFactory

logger = logging.getLogger(__name__)


@dataclass
class App:
    platform_config_factory: PlatformConfigFactory = None  # type: ignore
    helm_values_factory: HelmValuesFactory = None  # type: ignore
    helm_client: HelmClient = None  # type: ignore
    kube_client: KubeClient = None  # type: ignore
    status_manager: PlatformStatusManager = None  # type: ignore
    config_client: ConfigClient = None  # type: ignore
    raw_client: aiohttp.ClientSession = None  # type: ignore
    exit_stack: AsyncExitStack = field(default_factory=AsyncExitStack)

    async def close(self) -> None:
        await self.exit_stack.aclose()


config = Config.load_from_env()
app = App()


@kopf.on.startup()
async def startup(settings: kopf.OperatorSettings, **_: Any) -> None:
    app.platform_config_factory = PlatformConfigFactory(config)
    app.helm_client = HelmClient(namespace=config.platform_namespace)
    app.kube_client = await app.exit_stack.enter_async_context(
        KubeClient(config.kube_config),
    )
    node = await app.kube_client.get_node(config.node_name)
    app.helm_values_factory = HelmValuesFactory(
        config.helm_chart_names,
        container_runtime=node.container_runtime,
    )
    app.status_manager = PlatformStatusManager(
        app.kube_client, namespace=config.platform_namespace
    )
    app.config_client = await app.exit_stack.enter_async_context(
        ConfigClient(config.platform_config_url)
    )
    app.raw_client = await app.exit_stack.enter_async_context(aiohttp.ClientSession())

    settings.posting.level = logging.getLevelName(config.log_level)
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage()
    settings.persistence.diffbase_storage = kopf.AnnotationsDiffBaseStorage()

    # https://github.com/nolar/kopf/issues/232
    settings.watching.server_timeout = 5 * 60
    settings.watching.client_timeout = 5 * 60
    settings.watching.connect_timeout = 30
    settings.watching.reconnect_backoff = 1


@kopf.on.cleanup()
async def cleanup(**_: Any) -> None:
    await app.close()


@kopf.on.login()
def login(**_: Any) -> kopf.ConnectionInfo:
    return kopf.ConnectionInfo(
        server=str(config.kube_config.url),
        scheme="Bearer",
        ca_path=str(config.kube_config.cert_authority_path),
        token=config.kube_config.read_auth_token_from_path(),
        default_namespace=config.platform_namespace,
        expiration=datetime.fromtimestamp(
            config.kube_config.auth_token_exp_ts, tz=timezone.utc
        ),
    )


@kopf.on.create(  # type: ignore
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
@kopf.on.update(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def deploy(
    name: str, body: kopf.Body, logger: Logger, retry: int, **_: Any
) -> None:
    if retry > config.retries:
        await app.status_manager.fail_deployment(name)
        raise kopf.HandlerRetriesError(
            f"Platform deployment has exceeded {config.retries} retries"
        )

    async with app.kube_client.lock(
        config.platform_namespace,
        config.platform_lock_secret_name,
        "platform-deploy",
        ttl_s=15 * 60,
        sleep_s=3,
    ):
        await _deploy(name, body, logger, retry)


async def _deploy(name: str, body: kopf.Body, logger: Logger, retry: int) -> None:
    try:
        cluster = await get_cluster(name, body)
        platform = app.platform_config_factory.create(body, cluster)
    except asyncio.CancelledError:
        raise
    except aiohttp.ClientError:
        raise
    except Exception as ex:
        await app.status_manager.fail_deployment(name)
        raise kopf.PermanentError(f"Invalid platform configuration: {ex!s}")

    platform_deploy_failed = await is_platform_deploy_failed()

    if platform_deploy_failed:
        await app.status_manager.fail_deployment(name)
        raise kopf.PermanentError("Platform helm release failed")

    phase = await app.status_manager.get_phase(name)
    platform_deploy_required = await is_platform_deploy_required(platform, install=True)

    if phase == PlatformPhase.DEPLOYED and not platform_deploy_required:
        logger.info("Platform config didn't change, skipping platform deployment")
        return

    logger.info("Platform deployment started")

    await app.status_manager.start_deployment(platform.cluster_name, retry)

    if platform_deploy_required:
        await upgrade_platform_helm_release(platform)

    logger.info("Configuring cluster")
    await configure_cluster(cluster, platform)
    logger.info("Cluster configured")

    logger.info("Waiting for certificate")
    await wait_for_certificate_created(platform)
    logger.info("Certificate is ready")

    await complete_deployment(cluster, platform)

    logger.info("Platform deployment succeeded")


@kopf.on.delete(  # type: ignore
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def delete(
    name: str, body: kopf.Body, logger: Logger, retry: int, **_: Any
) -> None:
    if retry == 0:
        await app.status_manager.start_deletion(name)

    async with app.kube_client.lock(
        config.platform_namespace,
        config.platform_lock_secret_name,
        "platform-delete",
        ttl_s=15 * 60,
        sleep_s=3,
    ):
        await _delete(name, body, logger)


async def _delete(name: str, body: kopf.Body, logger: Logger) -> None:
    try:
        cluster = await get_cluster(name, body)
        platform = app.platform_config_factory.create(body, cluster)
    except aiohttp.ClientError:
        raise
    except asyncio.CancelledError:
        raise
    except Exception:
        # If platform has invalid configuration than there was no deployment
        # and no resources to delete. Platform resource can be safely deleted.
        logger.warning(
            "Platform has invalid configuration, delete handler cannot proceed"
        )
        return

    await app.helm_client.delete(config.helm_release_names.platform, wait=True)

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
                label_selector={"service": "platform-storage"},
            ),
            600,
        )
        logger.info("Platform storage pods deleted")
    except asyncio.TimeoutError:
        message = "Timeout error while wating for pods to be deleted"
        logger.error(message)
        raise kopf.TemporaryError(message)


@kopf.on.daemon(  # type: ignore
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def watch_config(
    name: str, body: kopf.Body, stopped: kopf.DaemonStopped, **_: Any
) -> None:
    logger = logging.getLogger("watch_config")

    logger.info("Started watching platform config")

    while True:
        # Async daemons do not need the `stopped` signal.
        # They can rely on `asyncio.CancelledError` raised.
        # Used in tests.
        if stopped:
            break

        logger.info(
            "Platform config will be checked in %d seconds",
            config.platform_config_watch_interval_s,
        )
        await asyncio.sleep(config.platform_config_watch_interval_s)

        try:
            async with app.kube_client.lock(
                config.platform_namespace,
                config.platform_lock_secret_name,
                "platform-watch",
                ttl_s=15 * 60,
                sleep_s=3,
            ):
                await _update(name, body, logger)
        except asyncio.CancelledError:
            logger.info("Stopped watching platform config")
            raise
        except Exception as exc:
            logger.warning("Watch iteration failed", exc_info=exc)


async def _update(name: str, body: kopf.Body, logger: Logger) -> None:
    phase = await app.status_manager.get_phase(name)

    if phase == PlatformPhase.PENDING:
        logger.info("Platform has not been installed yet, nothing to update")
        return

    if phase == PlatformPhase.DEPLOYING or phase == PlatformPhase.DELETING:
        logger.info("Cannot update platform while it is in %s phase", phase.value)
        return

    cluster = await get_cluster(name, body)
    platform = app.platform_config_factory.create(body, cluster)
    platform_deploy_failed = await is_platform_deploy_failed()

    if platform_deploy_failed:
        await app.status_manager.fail_deployment(name)
        logger.warning("Platform helm release failed, skipping platform config update")
        return

    platform_deploy_required = await is_platform_deploy_required(platform)

    if phase == PlatformPhase.DEPLOYED and not platform_deploy_required:
        logger.info("Platform config didn't change, skipping platform config update")
        return

    logger.info("Platform config update started")

    await app.status_manager.start_deployment(platform.cluster_name)

    try:
        if platform_deploy_required:
            await upgrade_platform_helm_release(platform)

        logger.info("Configuring cluster")
        await configure_cluster(cluster, platform)
        logger.info("Cluster configured")

        logger.info("Waiting for certificate")
        await wait_for_certificate_created(platform)
        logger.info("Certificate is ready")

        await complete_deployment(cluster, platform)

        logger.info("Platform config update succeeded")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error("Platform config update failed", exc_info=exc)
        await app.status_manager.fail_deployment(name)


async def get_cluster(name: str, body: kopf.Body) -> Cluster:
    token = body["spec"].get("token")
    return await app.config_client.get_cluster(name, token=token)


async def is_platform_deploy_required(
    platform: PlatformConfig, install: bool = False
) -> bool:
    return await is_helm_deploy_required(
        release_name=config.helm_release_names.platform,
        chart_name=config.helm_chart_names.platform,
        chart_version=config.helm_chart_versions.platform,
        values=app.helm_values_factory.create_platform_values(platform),
        install=install,
    )


async def is_helm_deploy_required(
    release_name: str,
    chart_name: str,
    chart_version: str,
    values: dict[str, Any],
    install: bool = False,
) -> bool:
    old_release = await app.helm_client.get_release(release_name)

    if not old_release:
        return install

    old_chart = old_release.chart
    old_release_values = await app.helm_client.get_release_values(release_name)
    new_chart = f"{chart_name}-{chart_version}"

    return old_chart != new_chart or old_release_values != values


async def is_platform_deploy_failed() -> bool:
    return await is_helm_deploy_failed(config.helm_release_names.platform)


async def is_helm_deploy_failed(release_name: str) -> bool:
    release = await app.helm_client.get_release(release_name)

    if not release:
        return False

    return release.status == ReleaseStatus.FAILED


async def create_storage_buckets(platform: PlatformConfig) -> None:
    if platform.monitoring.logs_bucket_name:
        if platform.buckets.provider == BucketsProvider.GCP:
            region = platform.monitoring.logs_region or platform.buckets.gcp_location
            access_key_id = platform.minio_gateway.root_user
            secret_access_key = platform.minio_gateway.root_user_password
            endpoint_url = platform.minio_gateway.endpoint_url
        elif platform.buckets.provider == BucketsProvider.AZURE:
            region = platform.buckets.azure_minio_gateway_region
            access_key_id = platform.minio_gateway.root_user
            secret_access_key = platform.minio_gateway.root_user_password
            endpoint_url = platform.minio_gateway.endpoint_url
        elif platform.buckets.provider == BucketsProvider.AWS:
            region = platform.buckets.aws_region
            access_key_id = None
            secret_access_key = None
            endpoint_url = None
        elif platform.buckets.provider == BucketsProvider.MINIO:
            region = platform.buckets.minio_region
            access_key_id = platform.buckets.minio_access_key
            secret_access_key = platform.buckets.minio_secret_key
            endpoint_url = platform.buckets.minio_url
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            region = platform.buckets.emc_ecs_region
            access_key_id = platform.buckets.emc_ecs_access_key_id
            secret_access_key = platform.buckets.emc_ecs_secret_access_key
            endpoint_url = platform.buckets.emc_ecs_s3_endpoint
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            region = platform.buckets.open_stack_region_name
            access_key_id = platform.buckets.open_stack_username
            secret_access_key = platform.buckets.open_stack_password
            endpoint_url = platform.buckets.open_stack_s3_endpoint
        else:
            raise ValueError(f"Unknown buckets provider: {platform.buckets.provider}")
        async with S3Client(
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        ) as s3_client:
            await s3_client.create_bucket(
                bucket_name=platform.monitoring.logs_bucket_name
            )


async def complete_deployment(cluster: Cluster, platform: PlatformConfig) -> None:
    await app.status_manager.complete_deployment(cluster.name)
    if cluster.cloud_provider and cluster.cloud_provider.storage:
        storage_names = [s.name for s in cluster.cloud_provider.storage.instances]
    else:
        storage_names = []
    for storage in platform.storages:
        storage_name = storage.path.lstrip("/") if storage.path else "default"
        if storage_name not in storage_names:
            continue
        await app.config_client.patch_storage(
            cluster_name=cluster.name,
            storage_name=storage_name,
            ready=True,
            token=platform.token,
        )

    await create_storage_buckets(platform)


async def upgrade_platform_helm_release(platform: PlatformConfig) -> None:
    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    ):
        await app.kube_client.update_service_account(
            namespace=platform.namespace,
            name=platform.service_account_name,
            annotations=platform.service_account_annotations,
            image_pull_secrets=platform.image_pull_secret_names,
        )
        await app.helm_client.upgrade(
            config.helm_release_names.platform,
            str(platform.helm_repo.url / config.helm_chart_names.platform),
            values=app.helm_values_factory.create_platform_values(platform),
            version=config.helm_chart_versions.platform,
            install=True,
            wait=True,
            timeout_s=600,
            username=platform.helm_repo.username,
            password=platform.helm_repo.password,
        )


async def wait_for_certificate_created(
    platform: PlatformConfig, timeout_s: float = 5 * 60
) -> None:
    if not platform.ingress_controller_install or not platform.ingress_acme_enabled:
        return

    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    ):
        await asyncio.wait_for(_wait_for_certificate_created(platform), timeout_s)


async def _wait_for_certificate_created(platform: PlatformConfig) -> None:
    ssl_context: ssl.SSLContext | None
    if platform.ingress_acme_environment == ACMEEnvironment.STAGING:
        ssl_context = ssl.create_default_context(cafile=config.acme_ca_staging_path)
    else:
        ssl_context = None

    while True:
        try:
            async with app.raw_client.get(
                platform.ingress_url, ssl_context=ssl_context
            ):
                return
        except ssl.SSLError:
            pass
        except aiohttp.ClientError:
            pass
        await asyncio.sleep(5)


async def configure_cluster(cluster: Cluster, platform: PlatformConfig) -> None:
    async with app.status_manager.transition(
        platform.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    ):
        await _configure_cluster(cluster, platform)


async def _configure_cluster(cluster: Cluster, platform: PlatformConfig) -> None:
    ingress_service: dict[str, Any] | None = None
    aws_ingress_lb: dict[str, Any] | None = None

    if platform.ingress_controller_install:
        ingress_service = await app.kube_client.get_service(
            namespace=platform.namespace, name=platform.ingress_service_name
        )
        if platform.kubernetes_provider == CloudProviderType.AWS:
            async with AwsElbClient(region=platform.aws_region) as client:
                aws_ingress_lb = await client.get_load_balancer_by_dns_name(
                    ingress_service.load_balancer_host
                )

    orchestrator = platform.create_patch_orchestrator_config_request(cluster)
    dns = platform.create_dns_config(
        ingress_service=ingress_service, aws_ingress_lb=aws_ingress_lb
    )
    await app.config_client.patch_cluster(
        platform.cluster_name,
        token=platform.token,
        request=PatchClusterRequest(orchestrator=orchestrator, dns=dns),
    )
