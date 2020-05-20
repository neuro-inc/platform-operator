from dataclasses import replace

import pytest

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import PlatformConfig


class TestHelmValuesFactory:
    @pytest.fixture
    def factory(self) -> HelmValuesFactory:
        return HelmValuesFactory()

    def test_create_platform_monitoring_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_MONITORING_K8S_NS": "platform-jobs",
            "NP_MONITORING_PLATFORM_API_URL": "https://dev.neu.ro/api/v1",
            "NP_MONITORING_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "NP_MONITORING_ES_HOSTS": "platform-elasticsearch-client:9200",
            "NP_MONITORING_REGISTRY_URL": (
                f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
            ),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
        }

    def test_create_on_prem_platform_monitoring_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(on_prem_platform_config)

        assert result["NP_MONITORING_K8S_KUBELET_PORT"] == 10250

    def test_create_on_prem_platform_monitoring_values_for_megafon_public(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
            replace(on_prem_platform_config, cluster_name="megafon-public")
        )

        assert result["NP_CORS_ORIGINS"] == (
            "https://megafon-release.neu.ro"
            ",http://megafon-neuro.netlify.app"
            ",https://release--neuro-web.netlify.app"
            ",https://app.neu.ro"
            ",https://app.ml.megafon.ru"
        )

    def test_create_on_prem_platform_monitoring_values_for_megafon_poc(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
            replace(on_prem_platform_config, cluster_name="megafon-poc")
        )

        assert result["NP_CORS_ORIGINS"] == (
            "https://megafon-release.neu.ro"
            ",http://megafon-neuro.netlify.app"
            ",https://release--neuro-web.netlify.app"
            ",https://app.neu.ro"
            ",https://app.ml.megafon.ru"
        )

    def test_create_ssh_auth_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_ssh_auth_values(gcp_platform_config)

        assert result == {
            "NP_AUTH_URL": "https://dev.neu.ro",
            "NP_PLATFORM_API_URL": "https://dev.neu.ro/api/v1",
            "NP_K8S_NS": "platform-jobs",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
        }

    def test_create_aws_ssh_auth_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_ssh_auth_values(aws_platform_config)

        assert result["service"] == {
            "annotations": {
                (
                    "service.beta.kubernetes.io/"
                    "aws-load-balancer-connection-idle-timeout"
                ): "3600"
            }
        }

    def test_create_on_prem_ssh_auth_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_ssh_auth_values(on_prem_platform_config)

        assert result["NODEPORT"] == 30022
