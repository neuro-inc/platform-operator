from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import replace
from typing import Any
from unittest import mock

import aiohttp
import kopf
import pytest
from neuro_config_client import (
    ConfigClient,
    PatchClusterRequest,
)

from platform_operator.aws_client import AwsElbClient, S3Client
from platform_operator.helm_client import HelmClient, Release, ReleaseStatus
from platform_operator.helm_values import HelmValuesFactory
from platform_operator.kube_client import (
    KubeClient,
    PlatformPhase,
    PlatformStatusManager,
    Service,
)
from platform_operator.models import (
    Cluster,
    Config,
    HelmChartNames,
    PlatformConfig,
    PlatformConfigFactory,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("setup_app")]


@pytest.fixture
def setup_app(
    config: Config,
    kube_client: KubeClient,
    status_manager: PlatformStatusManager,
    config_client: ConfigClient,
    helm_client: HelmClient,
    helm_values_factory: HelmValuesFactory,
) -> Iterator[None]:
    with mock.patch.object(Config, "load_from_env") as method:
        method.return_value = config

        from platform_operator.handlers import App

        with mock.patch("platform_operator.handlers.app", spec=App) as app:
            app.kube_client = kube_client
            app.status_manager = status_manager
            app.config_client = config_client
            app.helm_client = helm_client
            app.platform_config_factory = PlatformConfigFactory(config)
            app.helm_values_factory = helm_values_factory
            yield


@pytest.fixture
def kube_client() -> mock.AsyncMock:
    return mock.AsyncMock(KubeClient)


@pytest.fixture
def status_manager() -> Iterator[mock.Mock]:
    return mock.AsyncMock(PlatformStatusManager)


@pytest.fixture
def config_client() -> mock.Mock:
    return mock.AsyncMock(ConfigClient)


@pytest.fixture
def helm_client() -> mock.Mock:
    return mock.AsyncMock(HelmClient)


@pytest.fixture
def logger() -> logging.Logger:
    return logging.getLogger("controller")


@pytest.fixture
def raw_client() -> mock.AsyncMock:
    return mock.AsyncMock(aiohttp.ClientSession)


@pytest.fixture
def helm_values_factory() -> mock.Mock:
    return mock.AsyncMock(HelmValuesFactory)


@pytest.fixture
def is_platform_deploy_failed() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_platform_deploy_failed"
    ) as is_platform_deploy_failed:
        is_platform_deploy_failed.return_value = False
        yield is_platform_deploy_failed


@pytest.fixture
def is_platform_deploy_required() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_platform_deploy_required"
    ) as is_platform_deploy_required:
        yield is_platform_deploy_required


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
def aws_s3_client() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.S3Client", spec=S3Client
    ) as client_class:
        client_instance = mock.AsyncMock(S3Client)
        client_instance.__aenter__.return_value = client_instance
        client_class.return_value = client_instance
        yield client_instance


@pytest.fixture
def traefik_service() -> Service:
    return Service(
        {
            "spec": {"type": "LoadBalancer"},
            "status": {"loadBalancer": {"ingress": [{"ip": "192.168.0.1"}]}},
        }
    )


@pytest.fixture
def aws_traefik_service() -> Service:
    return Service(
        {
            "spec": {"type": "LoadBalancer"},
            "status": {"loadBalancer": {"ingress": [{"hostname": "traefik"}]}},
        }
    )


@pytest.fixture
def aws_traefik_lb() -> dict[str, Any]:
    return {
        "CanonicalHostedZoneId": "/hostedzone/traefik",
    }


@pytest.fixture
def stopped() -> kopf.DaemonStopped:
    stopped = mock.MagicMock()
    stopped.__bool__.side_effect = [False, True]
    return stopped


async def test_is_platform_deploy_required_on_install_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = None

    result = await _is_platform_deploy_required(gcp_platform_config, install=True)

    helm_client.get_release.assert_awaited_with(config.helm_release_names.platform)
    assert result is True


async def test_is_platform_deploy_required_on_install_false(
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = None

    result = await _is_platform_deploy_required(gcp_platform_config, install=False)

    assert result is False


async def test_is_platform_deploy_required_on_version_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = Release(
        name=config.helm_release_names.platform,
        namespace=config.platform_namespace,
        chart=f"{HelmChartNames.platform}-{config.helm_chart_versions.platform}-0",
        status=ReleaseStatus.DEPLOYED,
    )
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is True


async def test_is_platform_deploy_required_on_values_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = Release(
        name=config.helm_release_names.platform,
        namespace=config.platform_namespace,
        chart=f"{HelmChartNames.platform}-{config.helm_chart_versions.platform}",
        status=ReleaseStatus.DEPLOYED,
    )
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {"new": "value"}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is True


async def test_is_platform_deploy_required_no_update_false(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = Release(
        name=config.helm_release_names.platform,
        namespace=config.platform_namespace,
        chart=f"{HelmChartNames.platform}-{config.helm_chart_versions.platform}",
        status=ReleaseStatus.DEPLOYED,
    )
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is False


async def test_configure_aws_cluster(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    aws_elb_client: mock.Mock,
    aws_platform_config: PlatformConfig,
    aws_traefik_service: dict[str, Any],
    aws_traefik_lb: dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster

    kube_client.get_service.side_effect = [aws_traefik_service]
    aws_elb_client.get_load_balancer_by_dns_name.side_effect = [aws_traefik_lb]

    await configure_cluster(aws_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="traefik")]
    )
    aws_elb_client.get_load_balancer_by_dns_name.assert_has_awaits(
        [mock.call("traefik")]
    )
    config_client.patch_cluster.assert_awaited_with(
        aws_platform_config.cluster_name,
        PatchClusterRequest(
            dns=aws_platform_config.create_dns_config(
                ingress_service=aws_traefik_service,
                aws_ingress_lb=aws_traefik_lb,
            ),
        ),
        token=aws_platform_config.token,
    )


async def test_configure_cluster(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    gcp_platform_config: PlatformConfig,
    traefik_service: dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster

    kube_client.get_service.side_effect = [traefik_service]

    await configure_cluster(gcp_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="traefik")]
    )
    config_client.patch_cluster.assert_awaited_with(
        gcp_platform_config.cluster_name,
        PatchClusterRequest(
            dns=gcp_platform_config.create_dns_config(ingress_service=traefik_service),
        ),
        token=gcp_platform_config.token,
    )


async def test_configure_cluster_with_ingress_controller_disabled(
    config_client: mock.Mock,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import configure_cluster

    gcp_platform_config = replace(gcp_platform_config, ingress_controller_install=False)

    await configure_cluster(gcp_platform_config)

    config_client.patch_cluster.assert_awaited_with(
        gcp_platform_config.cluster_name,
        PatchClusterRequest(
            dns=gcp_platform_config.create_dns_config(),
        ),
        token=gcp_platform_config.token,
    )


async def test_deploy(
    status_manager: mock.AsyncMock,
    aws_s3_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    is_platform_deploy_failed.return_value = False
    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    is_platform_deploy_required.assert_awaited_once_with(
        gcp_platform_config, install=True
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )
    config_client.patch_storage.assert_not_awaited()

    kube_client.update_service_account.assert_awaited_once_with(
        namespace=gcp_platform_config.namespace,
        name=gcp_platform_config.service_account_name,
        annotations=gcp_platform_config.service_account_annotations,
        image_pull_secrets=gcp_platform_config.image_pull_secret_names,
    )

    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "https://ghcr.io/neuro-inc/helm-charts/platform",
        values=mock.ANY,
        version="1.0.0",
        install=True,
        wait=True,
        timeout_s=600,
        username=gcp_platform_config.helm_repo.username,
        password=gcp_platform_config.helm_repo.password,
    )

    config_client.patch_cluster.assert_awaited_once()

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )

    aws_s3_client.create_bucket.assert_awaited_once()


async def test_deploy_with_ingress_controller_disabled(
    aws_s3_client: mock.AsyncMock,
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    gcp_platform_body["spec"]["ingressController"] = {"enabled": False}
    gcp_platform_config = replace(gcp_platform_config, ingress_controller_install=False)

    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "https://ghcr.io/neuro-inc/helm-charts/platform",
        values=mock.ANY,
        version="1.0.0",
        install=True,
        wait=True,
        timeout_s=600,
        username=gcp_platform_config.helm_repo.username,
        password=gcp_platform_config.helm_repo.password,
    )

    config_client.patch_cluster.assert_awaited_once()

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    aws_s3_client.create_bucket.assert_awaited_once()


async def test_deploy_all_charts_deployed(
    aws_s3_client: mock.AsyncMock,
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    kube_client.update_service_account.assert_not_awaited()

    helm_client.upgrade.assert_not_awaited()

    config_client.patch_cluster.assert_awaited_once()

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    aws_s3_client.create_bucket.assert_awaited_once()


async def test_deploy_with_retries_exceeded(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    with pytest.raises(kopf.HandlerRetriesError):
        await deploy(  # type: ignore
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=config.retries + 1,
        )

    status_manager.fail_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_deploy_with_invalid_spec(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_platform_body: kopf.Body,
    cluster: Cluster,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    del gcp_platform_body["spec"]["monitoring"]

    config_client.get_cluster.return_value = cluster

    with pytest.raises(kopf.PermanentError, match="Invalid platform configuration"):
        await deploy(  # type: ignore
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=0,
        )

    status_manager.fail_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_deploy_no_changes(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    helm_client.upgrade.assert_not_awaited()

    config_client.patch_cluster.assert_not_awaited()

    status_manager.start_deployment.assert_not_awaited()
    status_manager.complete_deployment.assert_not_awaited()


async def test_deploy_platform_helm_release_failed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_platform_deploy_failed.return_value = True
    config_client.get_cluster.return_value = cluster

    with pytest.raises(kopf.PermanentError, match="Platform helm release failed"):
        await deploy(  # type: ignore
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=0,
        )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    status_manager.start_deployment.assert_not_awaited()


async def test_delete(
    status_manager: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = cluster

    await delete(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_awaited_once_with("platform", wait=True)

    status_manager.start_deletion.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_delete_on_prem(
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    on_prem_platform_body: kopf.Body,
    on_prem_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = cluster

    await delete(  # type: ignore
        name=on_prem_platform_config.cluster_name,
        body=on_prem_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_awaited_once_with("platform", wait=True)


async def test_delete_with_invalid_configuration(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    helm_client: mock.AsyncMock,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    del gcp_platform_body["spec"]["storages"]

    await delete(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    status_manager.start_deletion.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    helm_client.add_repo.assert_not_awaited()


async def test_watch(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_failed: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = cluster

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )
    config_client.patch_storage.assert_not_awaited()

    is_platform_deploy_failed.assert_awaited_once_with()

    is_platform_deploy_required.assert_awaited_once_with(gcp_platform_config)

    kube_client.update_service_account.assert_awaited_once_with(
        namespace=gcp_platform_config.namespace,
        name=gcp_platform_config.service_account_name,
        annotations=gcp_platform_config.service_account_annotations,
        image_pull_secrets=gcp_platform_config.image_pull_secret_names,
    )

    helm_client.upgrade.assert_has_awaits(
        [
            mock.call(
                "platform",
                "https://ghcr.io/neuro-inc/helm-charts/platform",
                values=mock.ANY,
                version="1.0.0",
                install=True,
                wait=True,
                timeout_s=600,
                username=gcp_platform_config.helm_repo.username,
                password=gcp_platform_config.helm_repo.password,
            ),
        ]
    )

    config_client.patch_cluster.assert_awaited_once()

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_watch_all_charts_deployed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = cluster

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    helm_client.upgrade.assert_not_awaited()

    config_client.patch_cluster.assert_awaited_once()

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_watch_no_changes(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = cluster

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    status_manager.start_deployment.assert_not_awaited()


@pytest.mark.parametrize(
    "platform_phase",
    [PlatformPhase.PENDING, PlatformPhase.DEPLOYING, PlatformPhase.DELETING],
)
async def test_watch_platform_deploying_deleting(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
    platform_phase: PlatformPhase,
) -> None:
    from platform_operator.handlers import watch

    status_manager.get_phase.return_value = platform_phase
    config_client.get_cluster.return_value = cluster

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    helm_client.add_repo.assert_not_awaited()
    status_manager.start_deployment.assert_not_awaited()


async def test_watch_platform_helm_release_failed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_failed: mock.AsyncMock,
    logger: logging.Logger,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_platform_deploy_failed.return_value = True
    config_client.get_cluster.return_value = cluster

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    config_client.get_cluster.assert_awaited_once_with(
        gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    status_manager.start_deployment.assert_not_awaited()


async def test_watch_ignores_error(
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    stopped: kopf.DaemonStopped,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    config_client.get_cluster.side_effect = Exception

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )


async def test_watch_update_failed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    logger: logging.Logger,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_required: mock.AsyncMock,
    cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch

    config_client.get_cluster.return_value = cluster
    is_platform_deploy_required.return_value = True
    helm_client.upgrade.side_effect = Exception

    await watch(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    status_manager.fail_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
