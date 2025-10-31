from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import aiohttp
import kopf
from neuro_config_client import (
    Cluster,
    ConfigClient,
)
from yarl import URL

from .aws_client import S3Client
from .helm_client import HelmClient, ReleaseStatus
from .helm_values import HelmValuesFactory
from .kube_client import (
    PLATFORM_API_VERSION,
    PLATFORM_GROUP,
    PLATFORM_PLURAL,
    KubeClient,
    PlatformPhase,
    PlatformStatusManager,
)
from .models import (
    BucketsProvider,
    Config,
    HelmChartNames,
    PlatformConfig,
    PlatformConfigFactory,
)


LOGGER = logging.getLogger(__name__)


@dataclass
class App:
    platform_config_factory: PlatformConfigFactory = None  # type: ignore
    helm_values_factory: HelmValuesFactory = None  # type: ignore
    helm_client: HelmClient = None  # type: ignore
    kube_client: KubeClient = None  # type: ignore
    status_manager: PlatformStatusManager = None  # type: ignore
    config_client: ConfigClient = None  # type: ignore
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
    app.helm_values_factory = HelmValuesFactory()
    app.status_manager = PlatformStatusManager(
        app.kube_client, namespace=config.platform_namespace
    )
    app.config_client = await app.exit_stack.enter_async_context(
        ConfigClient(config.platform_config_url)
    )

    settings.posting.level = getattr(logging, config.log_level)
    settings.posting.reporting_component = "apolo"
    settings.posting.reporting_instance = "apolo"
    settings.posting.event_name_prefix = "apolo-event-"
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
        expiration=datetime.fromtimestamp(config.kube_config.auth_token_exp_ts, tz=UTC),
    )


@kopf.on.create(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
@kopf.on.update(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def deploy(
    name: str | None, body: kopf.Body, logger: kopf.Logger, retry: int, **_: Any
) -> None:
    assert name, "Platform resource name is required"

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


async def _deploy(name: str, body: kopf.Body, logger: kopf.Logger, retry: int) -> None:
    try:
        cluster = await get_cluster(name, body)
        platform = app.platform_config_factory.create(body, cluster)
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
        LOGGER.info("Platform config didn't change, skipping platform deployment")
        return

    logger.info("Platform deployment started")

    await app.status_manager.start_deployment(platform.cluster_name, retry)

    try:
        if platform_deploy_required:
            await upgrade_platform_helm_release(platform)

        await complete_deployment(cluster, platform)

        logger.info("Platform deployment completed")
    except Exception as exc:
        logger.error("Platform deployment failed: %s", exc)
        LOGGER.exception("Platform deployment failed")
        raise kopf.TemporaryError(str(exc), delay=config.backoff)


@kopf.on.delete(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def delete(
    name: str | None, body: kopf.Body, logger: kopf.Logger, retry: int, **_: Any
) -> None:
    assert name, "Platform resource name is required"

    if retry == 0:
        await app.status_manager.start_deletion(name)

    async with app.kube_client.lock(
        config.platform_namespace,
        config.platform_lock_secret_name,
        "platform-delete",
        ttl_s=15 * 60,
        sleep_s=3,
    ):
        await app.helm_client.delete(config.helm_release_names.platform, wait=True)


@kopf.on.daemon(
    PLATFORM_GROUP, PLATFORM_API_VERSION, PLATFORM_PLURAL, backoff=config.backoff
)
async def watch(
    name: str | None,
    body: kopf.Body,
    stopped: kopf.DaemonStopped,
    logger: kopf.Logger,
    **_: Any,
) -> None:
    assert name, "Platform resource name is required"

    LOGGER.info("Started watching platform config")

    while True:
        # Async daemons do not need the `stopped` signal.
        # They can rely on `asyncio.CancelledError` raised.
        # Used in tests.
        if stopped:
            break

        LOGGER.info(
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
            LOGGER.info("Stopped watching platform config")
            raise
        except Exception as exc:
            LOGGER.warning("Watch iteration failed", exc_info=exc)


async def _update(name: str, body: kopf.Body, logger: kopf.Logger) -> None:
    phase = await app.status_manager.get_phase(name)

    if phase == PlatformPhase.PENDING:
        LOGGER.info("Platform has not been installed yet, nothing to update")
        return

    if phase == PlatformPhase.DEPLOYING or phase == PlatformPhase.DELETING:
        LOGGER.info("Cannot update platform while it is in %s phase", phase.value)
        return

    cluster = await get_cluster(name, body)
    platform = app.platform_config_factory.create(body, cluster)
    platform_deploy_failed = await is_platform_deploy_failed()

    if platform_deploy_failed:
        await app.status_manager.fail_deployment(name)
        logger.warning("Platform helm release failed, skipping platform update")
        return

    platform_deploy_required = await is_platform_deploy_required(platform)

    if phase == PlatformPhase.DEPLOYED and not platform_deploy_required:
        LOGGER.info("Platform config didn't change, skipping platform update")
        return

    logger.info("Platform deployment started")

    await app.status_manager.start_deployment(platform.cluster_name)

    try:
        if platform_deploy_required:
            await upgrade_platform_helm_release(platform)

        await complete_deployment(cluster, platform)

        logger.info("Platform deployment completed")
    except Exception as exc:
        logger.error("Platform deployment failed: %s", exc)
        LOGGER.exception("Platform deployment failed")
        await app.status_manager.fail_deployment(name)


async def get_cluster(name: str, body: kopf.Body) -> Cluster:
    token = body["spec"].get("token")
    return await app.config_client.get_cluster(name, token=token)


async def is_platform_deploy_required(
    platform: PlatformConfig, install: bool = False
) -> bool:
    return await is_helm_deploy_required(
        release_name=config.helm_release_names.platform,
        chart_name=HelmChartNames.platform,
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
    if not platform.monitoring.logs_bucket_name:
        return

    async with _create_buckets_s3_client(platform) as s3_client:
        await s3_client.create_bucket(bucket_name=platform.monitoring.logs_bucket_name)


@asynccontextmanager
async def _create_buckets_s3_client(
    platform: PlatformConfig,
) -> AsyncIterator[S3Client]:
    endpoint_url: URL | str | None

    if platform.buckets.provider == BucketsProvider.GCP:
        assert platform.minio_gateway
        region = platform.monitoring.logs_region or platform.buckets.gcp_location
        access_key_id = platform.minio_gateway.root_user
        secret_access_key = platform.minio_gateway.root_user_password
        endpoint_url = platform.minio_gateway.endpoint_url
    elif platform.buckets.provider == BucketsProvider.AZURE:
        assert platform.minio_gateway
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
        yield s3_client


async def complete_deployment(cluster: Cluster, platform: PlatformConfig) -> None:
    await app.status_manager.complete_deployment(cluster.name)
    await create_storage_buckets(platform)


async def upgrade_platform_helm_release(platform: PlatformConfig) -> None:
    await app.kube_client.update_service_account(
        namespace=platform.namespace,
        name=platform.service_account_name,
        annotations=platform.service_account_annotations,
        image_pull_secrets=platform.image_pull_secret_names,
    )
    await app.helm_client.upgrade(
        config.helm_release_names.platform,
        str(platform.helm_repo.url / HelmChartNames.platform),
        values=app.helm_values_factory.create_platform_values(platform),
        version=config.helm_chart_versions.platform,
        install=True,
        wait=True,
        timeout_s=600,
        username=platform.helm_repo.username,
        password=platform.helm_repo.password,
    )
