from dataclasses import replace

import pytest

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import PlatformConfig


class TestHelmValuesFactory:
    @pytest.fixture
    def factory(self) -> HelmValuesFactory:
        return HelmValuesFactory()

    def test_create_cluster_autoscaler_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(aws_platform_config)

        assert result == {
            "cloudProvider": "aws",
            "awsRegion": "us-east-1",
            "image": {"tag": "v1.13.9"},
            "rbac": {"create": True},
            "autoDiscovery": {"clusterName": aws_platform_config.cluster_name},
            "extraArgs": {
                "expander": "least-waste",
                "skip-nodes-with-local-storage": False,
                "skip-nodes-with-system-pods": False,
                "balance-similar-node-groups": True,
            },
        }

    def test_create_cluster_autoscaler_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(
            replace(
                aws_platform_config,
                aws=replace(
                    aws_platform_config.aws, role_auto_scaling_arn="auto_scaling_role"
                ),
            )
        )

        assert result["podAnnotations"] == {
            "iam.amazonaws.com/role": "auto_scaling_role"
        }

    def test_create_platform_storage_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_STORAGE_AUTH_URL": "https://dev.neu.ro",
            "NP_STORAGE_PVC_CLAIM_NAME": "platform-storage",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
        }

    def test_create_gcp_platform_object_storage_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_object_storage_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_OBSTORAGE_PROVIDER": "gcp",
            "NP_OBSTORAGE_AUTH_URL": "https://dev.neu.ro",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_OBSTORAGE_LOCATION": "us-central1",
            "NP_OBSTORAGE_GCP_PROJECT_ID": "project",
            "NP_OBSTORAGE_GCP_KEY_SECRET": "platform-blob-storage-key",
        }

    def test_create_aws_platform_object_storage_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_object_storage_values(aws_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": aws_platform_config.cluster_name,
            "NP_OBSTORAGE_PROVIDER": "aws",
            "NP_OBSTORAGE_AUTH_URL": "https://dev.neu.ro",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_OBSTORAGE_LOCATION": "us-east-1",
            "NP_OBSTORAGE_AWS_SECRET": "platform-blob-storage-key",
        }

    def test_create_aws_platform_object_storage_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_object_storage_values(
            replace(
                aws_platform_config,
                aws=replace(aws_platform_config.aws, role_s3_arn="s3_role"),
            )
        )

        assert result["annotations"] == {"iam.amazonaws.com/role": "s3_role"}

    def test_create_azure_platform_object_storage_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_object_storage_values(azure_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": azure_platform_config.cluster_name,
            "NP_OBSTORAGE_PROVIDER": "azure",
            "NP_OBSTORAGE_AUTH_URL": "https://dev.neu.ro",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_OBSTORAGE_LOCATION": "westus",
            "NP_OBSTORAGE_AZURE_SECRET": "platform-blob-storage-key",
        }

    def test_create_gcp_platform_registry_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(gcp_platform_config)

        assert result == {
            "INGRESS_HOST": f"registry.{gcp_platform_config.cluster_name}.org.neu.ro",
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES": 10000,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_REGISTRY_UPSTREAM_TYPE": "oauth",
            "NP_REGISTRY_UPSTREAM_URL": "https://gcr.io",
            "NP_REGISTRY_UPSTREAM_PROJECT": "project",
        }

    def test_create_aws_platform_registry_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(aws_platform_config)

        assert result == {
            "INGRESS_HOST": (f"registry.{aws_platform_config.cluster_name}.org.neu.ro"),
            "NP_CLUSTER_NAME": aws_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES": 1000,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_REGISTRY_UPSTREAM_TYPE": "aws_ecr",
            "NP_REGISTRY_UPSTREAM_URL": (
                "https://platform.dkr.ecr.us-east-1.amazonaws.com"
            ),
            "NP_REGISTRY_UPSTREAM_PROJECT": "neuro",
            "AWS_DEFAULT_REGION": "us-east-1",
        }

    def test_create_aws_platform_registry_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(
            replace(
                aws_platform_config,
                aws=replace(aws_platform_config.aws, role_ecr_arn="ecr_role"),
            )
        )

        assert result["annotations"] == {"iam.amazonaws.com/role": "ecr_role"}

    def test_create_azure_platform_registry_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(azure_platform_config)

        assert result == {
            "INGRESS_HOST": (
                f"registry.{azure_platform_config.cluster_name}.org.neu.ro"
            ),
            "NP_CLUSTER_NAME": azure_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES": 10000,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_REGISTRY_UPSTREAM_TYPE": "oauth",
            "NP_REGISTRY_UPSTREAM_URL": "https://platform.azurecr.io",
            "NP_REGISTRY_UPSTREAM_PROJECT": "neuro",
            "NP_REGISTRY_UPSTREAM_TOKEN_SERVICE": "platform.azurecr.io",
            "NP_REGISTRY_UPSTREAM_TOKEN_URL": (
                "https://platform.azurecr.io/oauth2/token"
            ),
        }

    def test_create_on_prem_platform_registry_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(on_prem_platform_config)

        assert result == {
            "INGRESS_HOST": (
                f"registry.{on_prem_platform_config.cluster_name}.org.neu.ro"
            ),
            "NP_CLUSTER_NAME": on_prem_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES": 10000,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_REGISTRY_UPSTREAM_TYPE": "basic",
            "NP_REGISTRY_UPSTREAM_URL": "http://platform-docker-registry:5000",
            "NP_REGISTRY_UPSTREAM_PROJECT": "neuro",
        }

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
