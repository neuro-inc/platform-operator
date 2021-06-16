import logging
from dataclasses import replace
from typing import Any, Dict, Iterator
from unittest import mock

import kopf
import pytest

from platform_operator.aws_client import AwsElbClient
from platform_operator.certificate_store import CertificateStore
from platform_operator.config_client import ConfigClient, NotificationType
from platform_operator.consul_client import ConsulClient
from platform_operator.helm_client import HelmClient
from platform_operator.helm_values import HelmValuesFactory
from platform_operator.kube_client import (
    KubeClient,
    PlatformConditionType,
    PlatformPhase,
    PlatformStatusManager,
)
from platform_operator.models import (
    Cluster,
    Config,
    PlatformConfig,
    PlatformConfigFactory,
)


pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("setup_app")]


@pytest.fixture
def setup_app(
    config: Config,
    consul_client: ConsulClient,
    kube_client: KubeClient,
    status_manager: PlatformStatusManager,
    config_client: ConfigClient,
    helm_client: HelmClient,
    helm_values_factory: HelmValuesFactory,
    certificate_store: CertificateStore,
) -> Iterator[None]:
    with mock.patch.object(Config, "load_from_env") as method:
        method.return_value = config

        from platform_operator.handlers import App

        with mock.patch("platform_operator.handlers.app", spec=App) as app:
            app.consul_client = consul_client
            app.kube_client = kube_client
            app.status_manager = status_manager
            app.config_client = config_client
            app.helm_client = helm_client
            app.certificate_store = certificate_store
            app.platform_config_factory = PlatformConfigFactory(config)
            app.helm_values_factory = helm_values_factory
            yield


@pytest.fixture
def consul_client() -> mock.AsyncMock:
    return mock.AsyncMock(ConsulClient)


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
def certificate_store() -> mock.Mock:
    return mock.AsyncMock(CertificateStore)


@pytest.fixture
def helm_values_factory() -> mock.Mock:
    return mock.AsyncMock(HelmValuesFactory)


@pytest.fixture
def is_obs_csi_driver_deploy_failed() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_obs_csi_driver_deploy_failed"
    ) as is_obs_csi_driver_deploy_failed:
        is_obs_csi_driver_deploy_failed.return_value = False
        yield is_obs_csi_driver_deploy_failed


@pytest.fixture
def is_platform_deploy_failed() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_platform_deploy_failed"
    ) as is_platform_deploy_failed:
        is_platform_deploy_failed.return_value = False
        yield is_platform_deploy_failed


@pytest.fixture
def is_obs_csi_driver_deploy_required() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_obs_csi_driver_deploy_required"
    ) as is_obs_csi_driver_deploy_required:
        yield is_obs_csi_driver_deploy_required


@pytest.fixture
def is_platform_deploy_required() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.is_platform_deploy_required"
    ) as is_platform_deploy_required:
        yield is_platform_deploy_required


@pytest.fixture
def configure_cluster() -> Iterator[mock.Mock]:
    with mock.patch(
        "platform_operator.handlers.configure_cluster"
    ) as configure_cluster:
        yield configure_cluster


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
def aws_traefik_service() -> Dict[str, Any]:
    return {
        "status": {"loadBalancer": {"ingress": [{"hostname": "platform-traefik"}]}},
    }


@pytest.fixture
def aws_traefik_lb() -> Dict[str, Any]:
    return {
        "CanonicalHostedZoneNameID": "/hostedzone/traefik",
    }


@pytest.fixture
def stopped() -> kopf.DaemonStopped:
    stopped = mock.MagicMock()
    stopped.__bool__.side_effect = [False, True]
    return stopped


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_on_install_true(
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    gcp_platform_config = replace(
        gcp_platform_config, gcp=replace(gcp_platform_config.gcp, storage_type="gcs")
    )
    helm_client.get_release.return_value = None

    result = await _is_obs_csi_driver_deploy_required(gcp_platform_config, install=True)

    assert result is True


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_on_install_false(
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    gcp_platform_config = replace(
        gcp_platform_config, gcp=replace(gcp_platform_config.gcp, storage_type="gcs")
    )
    helm_client.get_release.return_value = None

    result = await _is_obs_csi_driver_deploy_required(
        gcp_platform_config, install=False
    )

    assert result is False


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_on_version_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    gcp_platform_config = replace(
        gcp_platform_config, gcp=replace(gcp_platform_config.gcp, storage_type="gcs")
    )
    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.obs_csi_driver}"
            f"-{config.helm_chart_versions.obs_csi_driver}-0"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_obs_csi_driver_values.return_value = {}

    result = await _is_obs_csi_driver_deploy_required(gcp_platform_config)

    assert result is True


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_on_values_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    gcp_platform_config = replace(
        gcp_platform_config, gcp=replace(gcp_platform_config.gcp, storage_type="gcs")
    )
    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.obs_csi_driver}"
            f"-{config.helm_chart_versions.obs_csi_driver}"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_obs_csi_driver_values.return_value = {"new": "value"}

    result = await _is_obs_csi_driver_deploy_required(gcp_platform_config)

    assert result is True


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_no_update_false(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    gcp_platform_config = replace(
        gcp_platform_config, gcp=replace(gcp_platform_config.gcp, storage_type="gcs")
    )
    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.obs_csi_driver}"
            f"-{config.helm_chart_versions.obs_csi_driver}"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_obs_csi_driver_values.return_value = {}

    result = await _is_obs_csi_driver_deploy_required(gcp_platform_config)

    assert result is False


@pytest.mark.asyncio
async def test_is_obs_csi_driver_deploy_required_for_nfs_false(
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import (
        is_obs_csi_driver_deploy_required as _is_obs_csi_driver_deploy_required,
    )

    result = await _is_obs_csi_driver_deploy_required(gcp_platform_config)

    assert result is False


@pytest.mark.asyncio
async def test_is_platform_deploy_required_on_install_true(
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = None

    result = await _is_platform_deploy_required(gcp_platform_config, install=True)

    assert result is True


@pytest.mark.asyncio
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


@pytest.mark.asyncio
async def test_is_platform_deploy_required_on_version_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.platform}"
            f"-{config.helm_chart_versions.platform}-0"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is True


@pytest.mark.asyncio
async def test_is_platform_deploy_required_on_values_update_true(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.platform}"
            f"-{config.helm_chart_versions.platform}"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {"new": "value"}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is True


@pytest.mark.asyncio
async def test_is_platform_deploy_required_no_update_false(
    config: Config,
    gcp_platform_config: PlatformConfig,
    helm_client: mock.AsyncMock,
    helm_values_factory: mock.AsyncMock,
) -> None:
    from platform_operator.handlers import (
        is_platform_deploy_required as _is_platform_deploy_required,
    )

    helm_client.get_release.return_value = {
        "Chart": (
            f"{config.helm_chart_names.platform}"
            f"-{config.helm_chart_versions.platform}"
        )
    }
    helm_client.get_release_values.return_value = {}
    helm_values_factory.create_platform_values.return_value = {}

    result = await _is_platform_deploy_required(gcp_platform_config)

    assert result is False


@pytest.mark.asyncio
async def test_configure_aws_cluster(
    kube_client: mock.Mock,
    config_client: mock.Mock,
    aws_elb_client: mock.Mock,
    aws_platform_config: PlatformConfig,
    aws_traefik_service: Dict[str, Any],
    aws_traefik_lb: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    kube_client.get_service.side_effect = [aws_traefik_service]
    aws_elb_client.get_load_balancer_by_dns_name.side_effect = [aws_traefik_lb]

    await _configure_cluster(aws_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="platform-traefik")]
    )
    aws_elb_client.get_load_balancer_by_dns_name.assert_has_awaits(
        [mock.call("platform-traefik")]
    )
    config_client.patch_cluster.assert_awaited_with(
        cluster_name=aws_platform_config.cluster_name,
        token=aws_platform_config.token,
        payload=aws_platform_config.create_cluster_config(
            traefik_service=aws_traefik_service,
            aws_traefik_lb=aws_traefik_lb,
        ),
    )


@pytest.mark.asyncio
async def test_configure_cluster(
    gcp_platform_config: PlatformConfig,
    kube_client: mock.Mock,
    config_client: mock.Mock,
    traefik_service: Dict[str, Any],
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    kube_client.get_service.side_effect = [traefik_service]

    await _configure_cluster(gcp_platform_config)

    kube_client.get_service.assert_has_awaits(
        [mock.call(namespace="platform", name="platform-traefik")]
    )
    config_client.patch_cluster.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_cluster_config(
            traefik_service=traefik_service,
        ),
    )


@pytest.mark.asyncio
async def test_configure_cluster_with_ingress_controller_disabled(
    gcp_platform_config: PlatformConfig,
    config_client: mock.Mock,
) -> None:
    from platform_operator.handlers import configure_cluster as _configure_cluster

    gcp_platform_config = replace(gcp_platform_config, ingress_controller_enabled=False)

    await _configure_cluster(gcp_platform_config)

    config_client.patch_cluster.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        payload=gcp_platform_config.create_cluster_config(),
    )


@pytest.mark.asyncio
async def test_deploy(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    is_platform_deploy_failed.return_value = False
    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    is_platform_deploy_required.assert_awaited_once_with(
        gcp_platform_config, install=True
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )
    config_client.send_notification.assert_has_awaits(
        [
            mock.call(
                cluster_name=gcp_platform_config.cluster_name,
                token=gcp_platform_config.token,
                notification_type=NotificationType.CLUSTER_UPDATING,
            ),
            mock.call(
                cluster_name=gcp_platform_config.cluster_name,
                token=gcp_platform_config.token,
                notification_type=NotificationType.CLUSTER_UPDATE_SUCCEEDED,
            ),
        ]
    )

    kube_client.update_service_account_image_pull_secrets.assert_awaited_once_with(
        namespace=gcp_platform_config.namespace,
        name=gcp_platform_config.service_account_name,
        image_pull_secrets=gcp_platform_config.image_pull_secret_names,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "neuro/platform",
        values=mock.ANY,
        version="1.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )

    certificate_store.wait_till_certificate_created.assert_awaited_once()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


@pytest.mark.asyncio
async def test_deploy_with_ingress_controller_disabled(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    gcp_platform_body["spec"]["kubernetes"]["ingressController"] = {"enabled": False}
    gcp_platform_config = replace(gcp_platform_config, ingress_controller_enabled=False)

    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_awaited_once_with(
        "platform",
        "neuro/platform",
        values=mock.ANY,
        version="1.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )

    certificate_store.wait_till_certificate_created.assert_not_awaited()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    )
    assert status_manager.transition.call_count == 2
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


@pytest.mark.asyncio
async def test_deploy_gcp_with_gcs_storage(
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    is_obs_csi_driver_deploy_failed: mock.AsyncMock,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    is_obs_csi_driver_deploy_failed.return_value = False
    is_obs_csi_driver_deploy_required.return_value = True
    config_client.get_cluster.return_value = gcp_cluster
    gcp_platform_body["spec"]["storage"] = {"gcs": {"bucket": "storage"}}
    gcp_platform_config = replace(
        gcp_platform_config,
        gcp=replace(
            gcp_platform_config.gcp,
            storage_type="gcs",
            storage_nfs_server="",
            storage_nfs_path="/",
            storage_gcs_bucket_name="storage",
        ),
    )

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    is_obs_csi_driver_deploy_required.assert_awaited_once_with(
        gcp_platform_config, install=True
    )

    helm_client.upgrade.assert_any_await(
        "platform-obs-csi-driver",
        "neuro/obs-csi-driver",
        values=mock.ANY,
        version="2.0.0",
        namespace="platform",
        install=True,
        wait=True,
        timeout=600,
    )


@pytest.mark.asyncio
async def test_deploy_all_charts_deployed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    is_obs_csi_driver_deploy_required.return_value = False
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    kube_client.update_service_account_image_pull_secrets.assert_not_awaited()

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_not_awaited()

    certificate_store.wait_till_certificate_created.assert_awaited_once()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    )


@pytest.mark.asyncio
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
    config_client.send_notification.assert_any_await(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        notification_type=NotificationType.CLUSTER_UPDATE_FAILED,
    )


@pytest.mark.asyncio
async def test_deploy_with_invalid_spec(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    del gcp_platform_body["spec"]["storage"]

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


@pytest.mark.asyncio
async def test_deploy_no_changes(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_obs_csi_driver_deploy_required.return_value = False
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await deploy(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_body["spec"]["token"],
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_not_awaited()

    certificate_store.wait_till_certificate_created.assert_not_awaited()
    configure_cluster.assert_not_awaited()

    status_manager.start_deployment.assert_not_awaited()
    status_manager.complete_deployment.assert_not_awaited()


@pytest.mark.parametrize(
    "obs_csi_driver_deploy_failed,platform_deploy_failed",
    [(True, True), (False, True), (True, False)],
)
async def test_deploy_helm_release_failed(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    is_obs_csi_driver_deploy_failed: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
    obs_csi_driver_deploy_failed: bool,
    platform_deploy_failed: bool,
) -> None:
    from platform_operator.handlers import deploy

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_obs_csi_driver_deploy_failed.return_value = obs_csi_driver_deploy_failed
    is_platform_deploy_failed.return_value = platform_deploy_failed
    config_client.get_cluster.return_value = gcp_cluster

    with pytest.raises(kopf.PermanentError, match="One of helm releases failed"):
        await deploy(  # type: ignore
            name=gcp_platform_config.cluster_name,
            body=gcp_platform_body,
            logger=logger,
            retry=0,
        )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    status_manager.start_deployment.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete(
    status_manager: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = gcp_cluster

    await delete(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.delete.assert_awaited_once_with("platform", purge=True)

    kube_client.wait_till_pods_deleted.assert_has_awaits(
        [
            mock.call(namespace="platform-jobs"),
            mock.call(
                namespace="platform", label_selector={"service": "platformstorageapi"}
            ),
        ]
    )

    status_manager.start_deletion.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


@pytest.mark.asyncio
async def test_delete_gcp_with_gcs_storage(
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = gcp_cluster
    gcp_platform_body["spec"]["storage"] = {"gcs": {"bucket": "storage"}}

    await delete(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_has_awaits(
        [
            mock.call("platform", purge=True),
            mock.call("platform-obs-csi-driver", purge=True),
        ]
    )


@pytest.mark.asyncio
async def test_delete_on_prem(
    helm_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    on_prem_cluster: Cluster,
    on_prem_platform_body: kopf.Body,
    on_prem_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    config_client.get_cluster.return_value = on_prem_cluster

    await delete(  # type: ignore
        name=on_prem_platform_config.cluster_name,
        body=on_prem_platform_body,
        logger=logger,
        retry=0,
    )

    helm_client.delete.assert_has_awaits(
        [
            mock.call("platform", purge=True),
        ]
    )


@pytest.mark.asyncio
async def test_delete_with_invalid_configuration(
    status_manager: mock.AsyncMock,
    logger: logging.Logger,
    helm_client: mock.AsyncMock,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import delete

    del gcp_platform_body["spec"]["storage"]

    await delete(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        retry=0,
    )

    status_manager.start_deletion.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    helm_client.init.assert_not_awaited()


@pytest.mark.asyncio
async def test_watch_config(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    kube_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_obs_csi_driver_deploy_failed: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch_config

    is_obs_csi_driver_deploy_required.return_value = True
    is_platform_deploy_required.return_value = True
    config_client.get_cluster.return_value = gcp_cluster

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )
    config_client.send_notification.assert_has_awaits(
        [
            mock.call(
                cluster_name=gcp_platform_config.cluster_name,
                token=gcp_platform_config.token,
                notification_type=NotificationType.CLUSTER_UPDATING,
            ),
            mock.call(
                cluster_name=gcp_platform_config.cluster_name,
                token=gcp_platform_config.token,
                notification_type=NotificationType.CLUSTER_UPDATE_SUCCEEDED,
            ),
        ]
    )

    is_obs_csi_driver_deploy_failed.assert_awaited_once_with()
    is_platform_deploy_failed.assert_awaited_once_with()

    is_obs_csi_driver_deploy_required.assert_awaited_once_with(gcp_platform_config)
    is_platform_deploy_required.assert_awaited_once_with(gcp_platform_config)

    kube_client.update_service_account_image_pull_secrets.assert_awaited_once_with(
        namespace=gcp_platform_config.namespace,
        name=gcp_platform_config.service_account_name,
        image_pull_secrets=gcp_platform_config.image_pull_secret_names,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_has_awaits(
        [
            mock.call(
                "platform-obs-csi-driver",
                "neuro/obs-csi-driver",
                values=mock.ANY,
                version="2.0.0",
                namespace="platform",
                install=True,
                wait=True,
                timeout=600,
            ),
            mock.call(
                "platform",
                "neuro/platform",
                values=mock.ANY,
                version="1.0.0",
                namespace="platform",
                install=True,
                wait=True,
                timeout=600,
            ),
        ]
    )

    certificate_store.wait_till_certificate_created.assert_awaited_once()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.PLATFORM_DEPLOYED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )


async def test_watch_config_all_charts_deployed(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    certificate_store: mock.AsyncMock,
    configure_cluster: mock.AsyncMock,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch_config

    is_obs_csi_driver_deploy_required.return_value = False
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()
    helm_client.upgrade.assert_not_awaited()

    certificate_store.wait_till_certificate_created.assert_awaited_once()
    configure_cluster.assert_awaited_once_with(gcp_platform_config)

    status_manager.start_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name, 0
    )
    status_manager.complete_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CERTIFICATE_CREATED
    )
    status_manager.transition.assert_any_call(
        gcp_platform_config.cluster_name, PlatformConditionType.CLUSTER_CONFIGURED
    )


async def test_watch_config_no_changes(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_obs_csi_driver_deploy_required: mock.AsyncMock,
    is_platform_deploy_required: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch_config

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_obs_csi_driver_deploy_required.return_value = False
    is_platform_deploy_required.return_value = False
    config_client.get_cluster.return_value = gcp_cluster

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()

    status_manager.start_deployment.assert_not_awaited()


@pytest.mark.parametrize(
    "platform_phase",
    [PlatformPhase.PENDING, PlatformPhase.DEPLOYING, PlatformPhase.DELETING],
)
async def test_watch_config_platform_deploying_deleting(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    logger: logging.Logger,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
    platform_phase: PlatformPhase,
) -> None:
    from platform_operator.handlers import watch_config

    status_manager.get_phase.return_value = platform_phase
    config_client.get_cluster.return_value = gcp_cluster

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    consul_client.wait_healthy.assert_called_once()
    helm_client.init.assert_not_awaited()
    status_manager.start_deployment.assert_not_awaited()


@pytest.mark.parametrize(
    "obs_csi_driver_deploy_failed,platform_deploy_failed",
    [(True, True), (False, True), (True, False)],
)
async def test_watch_config_helm_release_failed(
    status_manager: mock.AsyncMock,
    consul_client: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    stopped: kopf.DaemonStopped,
    is_obs_csi_driver_deploy_failed: mock.AsyncMock,
    is_platform_deploy_failed: mock.AsyncMock,
    logger: logging.Logger,
    config: Config,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
    obs_csi_driver_deploy_failed: bool,
    platform_deploy_failed: bool,
) -> None:
    from platform_operator.handlers import watch_config

    status_manager.get_phase.return_value = PlatformPhase.DEPLOYED
    is_obs_csi_driver_deploy_failed.return_value = obs_csi_driver_deploy_failed
    is_platform_deploy_failed.return_value = platform_deploy_failed
    config_client.get_cluster.return_value = gcp_cluster

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    consul_client.wait_healthy.assert_called_once()

    config_client.get_cluster.assert_awaited_once_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
    )

    helm_client.init.assert_awaited_once_with(client_only=True, skip_refresh=True)
    helm_client.add_repo.assert_has_awaits(
        [mock.call(config.helm_stable_repo), mock.call(gcp_platform_config.helm_repo)]
    )
    helm_client.update_repo.assert_awaited_once()

    status_manager.start_deployment.assert_not_awaited()


@pytest.mark.asyncio
async def test_watch_config_ignores_error(
    config_client: mock.AsyncMock,
    logger: logging.Logger,
    stopped: kopf.DaemonStopped,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch_config

    config_client.get_cluster.side_effect = Exception

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )


@pytest.mark.asyncio
async def test_watch_config_update_failed(
    status_manager: mock.AsyncMock,
    config_client: mock.AsyncMock,
    helm_client: mock.AsyncMock,
    logger: logging.Logger,
    stopped: kopf.DaemonStopped,
    is_platform_deploy_required: mock.AsyncMock,
    gcp_cluster: Cluster,
    gcp_platform_body: kopf.Body,
    gcp_platform_config: PlatformConfig,
) -> None:
    from platform_operator.handlers import watch_config

    config_client.get_cluster.return_value = gcp_cluster
    is_platform_deploy_required.return_value = True
    helm_client.upgrade.side_effect = Exception

    await watch_config(  # type: ignore
        name=gcp_platform_config.cluster_name,
        body=gcp_platform_body,
        logger=logger,
        stopped=stopped,
    )

    status_manager.fail_deployment.assert_awaited_once_with(
        gcp_platform_config.cluster_name
    )

    config_client.send_notification.assert_awaited_with(
        cluster_name=gcp_platform_config.cluster_name,
        token=gcp_platform_config.token,
        notification_type=NotificationType.CLUSTER_UPDATE_FAILED,
    )
