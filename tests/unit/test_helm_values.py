import re
from dataclasses import replace
from typing import Any
from unittest import mock

import pytest
from neuro_config_client import ACMEEnvironment, IdleJobConfig, Resources
from yarl import URL

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import (
    BucketsConfig,
    BucketsProvider,
    DockerConfig,
    DockerRegistryStorageDriver,
    DockerRegistryType,
    ExternalSecretObjectsSpec,
    ExternalSecretsSpec,
    IngressServiceType,
    LabelsConfig,
    PlatformConfig,
    PlatformStorageSpec,
)


class TestHelmValuesFactory:
    @pytest.fixture
    def factory(self) -> HelmValuesFactory:
        return HelmValuesFactory()

    def test_create_gcp_platform_values(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(gcp_platform_config)

        assert result == {
            "traefikEnabled": True,
            "acmeEnabled": True,
            "dockerRegistryEnabled": False,
            "harborEnabled": False,
            "appsPostgresOperatorEnabled": True,
            "appsSparkOperatorEnabled": True,
            "appsKedaEnabled": True,
            "minioEnabled": False,
            "minioGatewayEnabled": True,
            "platformReportsEnabled": True,
            "lokiEnabled": True,
            "alloyEnabled": True,
            "externalSecretsEnabled": True,
            "alpineImage": {"repository": "ghcr.io/neuro-inc/alpine"},
            "pauseImage": {"repository": "ghcr.io/neuro-inc/pause"},
            "crictlImage": {"repository": "ghcr.io/neuro-inc/crictl"},
            "kubectlImage": {"repository": "ghcr.io/neuro-inc/kubectl"},
            "clusterName": cluster_name,
            "serviceToken": "token",
            "nodePools": [
                {"name": "test-node-pool", "idleSize": 0, "cpu": 1.0, "nvidiaGpu": 1}
            ],
            "nodeLabels": {
                "nodePool": "platform.neuromation.io/nodepool",
                "job": "platform.neuromation.io/job",
                "gpu": "platform.neuromation.io/accelerator",
            },
            "imagesPrepull": {
                "refreshInterval": "1h",
                "images": [{"image": "neuromation/base"}],
            },
            "dockerConfigSecret": {
                "create": True,
                "name": "platform-docker-config",
                "credentials": {
                    "url": "https://ghcr.io/neuro-inc",
                    "email": f"{cluster_name}@neu.ro",
                    "username": cluster_name,
                    "password": "password",
                },
            },
            "dockerHubConfigSecret": {
                "create": True,
                "name": "platform-docker-hub-config",
                "credentials": {
                    "url": "https://index.docker.io/v1/",
                    "email": f"{cluster_name}@neu.ro",
                    "username": cluster_name,
                    "password": "password",
                },
            },
            "serviceAccount": {"annotations": {}},
            "ingress": {
                "jobFallbackHost": "default.jobs-dev.neu.ro",
                "registryHost": f"registry.{cluster_name}.org.neu.ro",
                "ingressAuthHost": "platformingressauth",
                "cors": {
                    "originList": [
                        "https://console.apolo.us",
                        "https://custom.app",
                    ],
                    "originListRegex": [
                        f"https:\\/\\/[a-zA-Z0-9_-]+\\.jobs\\.{re.escape(cluster_name)}\\.org\\.neu\\.ro",
                        f"https:\\/\\/[a-zA-Z0-9_-]+\\.apps\\.{re.escape(cluster_name)}\\.org\\.neu\\.ro",
                    ],
                },
            },
            "jobs": {
                "namespace": {"create": True, "name": "platform-jobs"},
                "label": "platform.neuromation.io/job",
            },
            "idleJobs": [
                {
                    "name": "miner",
                    "count": 1,
                    "image": "miner",
                    "resources": {"cpu": "1000m", "memory": str(2**30)},
                }
            ],
            "storages": [
                {
                    "path": "",
                    "size": "10Gi",
                    "nfs": {"server": "192.168.0.3", "path": "/"},
                }
            ],
            "alertmanager": {
                "config": {
                    "route": {
                        "receiver": "platform-notifications",
                        "group_wait": "30s",
                        "group_interval": "5m",
                        "repeat_interval": "4h",
                        "group_by": ["alertname"],
                        "routes": [
                            {
                                "receiver": "ignore",
                                "matchers": [
                                    'exported_service="default-backend@kubernetes"'
                                ],
                                "continue": False,
                            },
                            {
                                "receiver": "ignore",
                                "matchers": ['exported_service=~"platform-jobs-.+"'],
                                "continue": False,
                            },
                            {
                                "receiver": "ignore",
                                "matchers": ['namespace="platform-jobs"'],
                                "continue": False,
                            },
                        ],
                    },
                    "receivers": [
                        {"name": "ignore"},
                        {
                            "name": "platform-notifications",
                            "webhook_configs": [
                                {
                                    "url": (
                                        "https://dev.neu.ro/api"
                                        "/v1/notifications/alert-manager-notification"
                                    ),
                                    "http_config": {
                                        "authorization": {
                                            "type": "Bearer",
                                            "credentials_file": (
                                                "/etc/alertmanager"
                                                "/secrets/platform-token/token"
                                            ),
                                        }
                                    },
                                }
                            ],
                        },
                    ],
                }
            },
            "federatedPrometheus": {
                "auth": {
                    "username": "prometheus-admin",
                    "password": "prometheus-password",
                }
            },
            "ssl": {"cert": "", "key": ""},
            "clusterSecretStore": mock.ANY,
            "externalSecretObjects": mock.ANY,
            "acme": mock.ANY,
            "traefik": mock.ANY,
            "minio-gateway": mock.ANY,
            "platform-storage": mock.ANY,
            "platform-registry": mock.ANY,
            "platform-monitoring": mock.ANY,
            "platform-container-runtime": mock.ANY,
            "platform-secrets": mock.ANY,
            "platform-reports": mock.ANY,
            "platform-disks": mock.ANY,
            "platform-api-poller": mock.ANY,
            "platform-buckets": mock.ANY,
            "platform-metadata": mock.ANY,
            "loki": mock.ANY,
            "alloy": mock.ANY,
            "spark-operator": mock.ANY,
            "external-secrets": mock.ANY,
        }

    def test_create_gcp_platform_with_ssl_cert(
        self,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        gcp_platform_config = replace(
            gcp_platform_config,
            ingress_acme_enabled=False,
            ingress_ssl_cert_data="cert_data",
            ingress_ssl_cert_key_data="key_data",
        )

        result = factory.create_platform_values(gcp_platform_config)

        assert result["ssl"] == {"cert": "cert_data", "key": "key_data"}
        assert result["acmeEnabled"] is False
        assert "acme" not in result

    def test_create_gcp_platform_values_with_idle_jobs(
        self,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        gcp_platform_config = replace(
            gcp_platform_config,
            idle_jobs=[
                IdleJobConfig(
                    name="miner",
                    count=1,
                    image="miner",
                    resources=Resources(cpu=1, memory=2**30, nvidia_gpu=1),
                ),
                IdleJobConfig(
                    name="miner",
                    count=1,
                    image="miner",
                    command=["bash"],
                    args=["-c", "sleep infinity"],
                    image_pull_secret="secret",
                    resources=Resources(cpu=1, memory=2**30, nvidia_gpu=1),
                    env={"NAME": "VALUE"},
                    node_selector={"gpu": "nvidia-tesla-k80"},
                ),
            ],
        )

        result = factory.create_platform_values(gcp_platform_config)

        assert result["idleJobs"] == [
            {
                "name": "miner",
                "count": 1,
                "image": "miner",
                "resources": {
                    "cpu": "1000m",
                    "memory": str(2**30),
                    "nvidia.com/gpu": 1,
                },
            },
            {
                "name": "miner",
                "count": 1,
                "image": "miner",
                "command": ["bash"],
                "args": ["-c", "sleep infinity"],
                "imagePullSecrets": [{"name": "secret"}],
                "resources": {
                    "cpu": "1000m",
                    "memory": str(2**30),
                    "nvidia.com/gpu": 1,
                },
                "env": {"NAME": "VALUE"},
                "nodeSelector": {"gpu": "nvidia-tesla-k80"},
            },
        ]

    def test_create_gcp_platform_values_without_docker_config_secret(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                docker_config=DockerConfig(
                    url=URL("https://ghcr.io/neuro-inc"),
                    secret_name="secret",
                    create_secret=False,
                ),
            )
        )

        assert result["dockerConfigSecret"] == {"create": False}

    def test_create_gcp_platform_values_without_docker_hub_config_secret(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(gcp_platform_config, docker_hub_config=None)
        )

        assert result["dockerHubConfigSecret"] == {"create": False}

    def test_create_aws_platform_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                aws_platform_config, service_account_annotations={"role-arn": "role"}
            )
        )

        assert factory.create_platform_values(aws_platform_config)

        assert result["serviceAccount"] == {"annotations": {"role-arn": "role"}}

    def test_create_on_prem_platform_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(on_prem_platform_config)

        assert result["storages"] == [
            {
                "path": "",
                "size": "10Gi",
                "nfs": {"server": "192.168.0.3", "path": "/"},
            }
        ]
        assert result["dockerRegistryEnabled"] is True
        assert result["appsKedaEnabled"] is True
        assert result["appsPostgresOperatorEnabled"] is True
        assert result["appsSparkOperatorEnabled"] is True
        assert "docker-registry" in result
        assert result["minioEnabled"] is True
        assert (
            result["ingress"]["minioHost"]
            == f"blob.{on_prem_platform_config.cluster_name}.org.neu.ro"
        )
        assert "minio" in result
        assert "platform-object-storage" not in result

    def test_create_on_prem_platform_values_without_docker_registry(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                registry=replace(
                    on_prem_platform_config.registry, docker_registry_install=False
                ),
            )
        )

        assert result["dockerRegistryEnabled"] is False
        assert "docker-registry" not in result

    def test_create_on_prem_platform_values_with_harbor_registry(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                registry=replace(
                    on_prem_platform_config.registry,
                    docker_registry_type=DockerRegistryType.HARBOR,
                ),
            )
        )

        assert result["dockerRegistryEnabled"] is False
        assert result["harborEnabled"] is True
        assert "harbor" in result
        assert "docker-registry" not in result

    def test_create_on_prem_platform_values_with_docker_registry_explicit(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                registry=replace(
                    on_prem_platform_config.registry,
                    docker_registry_type=DockerRegistryType.DOCKER,
                ),
            )
        )

        assert result["dockerRegistryEnabled"] is True
        assert result["harborEnabled"] is False
        assert "docker-registry" in result
        assert "harbor" not in result

    def test_create_on_prem_platform_values_without_minio(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                buckets=replace(on_prem_platform_config.buckets, minio_install=False),
            )
        )

        assert result["minioEnabled"] is False
        assert "minio" not in result

    def test_create_on_prem_platform_values_without_platform_reports(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                monitoring=replace(
                    on_prem_platform_config.monitoring, metrics_enabled=False
                ),
            )
        )

        assert result["platformReportsEnabled"] is False
        assert "alertmanager" not in result
        assert "platform-reports" not in result

    def test_create_platform_values_without_notifications_url(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, notifications_url=URL("-"))

        result = factory.create_platform_values(gcp_platform_config)

        assert result["alertmanager"] == {}

    def test_create_acme_values(
        self,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        cluster_name = gcp_platform_config.cluster_name
        result = factory.create_acme_values(gcp_platform_config)

        assert result == {
            "nameOverride": "acme",
            "fullnameOverride": "acme",
            "bashImage": {"repository": "ghcr.io/neuro-inc/bash"},
            "acme": {
                "email": f"{cluster_name}@neu.ro",
                "dns": "neuro",
                "server": "letsencrypt",
                "domains": [
                    f"{cluster_name}.org.neu.ro",
                    f"*.{cluster_name}.org.neu.ro",
                    f"*.jobs.{cluster_name}.org.neu.ro",
                    f"*.apps.{cluster_name}.org.neu.ro",
                ],
                "sslCertSecretName": "platform-ssl-cert",
            },
            "podLabels": {"service": "acme"},
            "env": [
                {"name": "NEURO_URL", "value": "https://dev.neu.ro"},
                {"name": "NEURO_CLUSTER", "value": cluster_name},
                {
                    "name": "NEURO_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {"key": "token", "name": "platform-token"}
                    },
                },
            ],
            "persistence": {"storageClassName": "platform-standard-topology-aware"},
            "priorityClassName": "platform-services",
        }

    def test_create_acme_values_with_acme_staging(
        self,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        gcp_platform_config = replace(
            gcp_platform_config, ingress_acme_environment=ACMEEnvironment.STAGING
        )

        result = factory.create_acme_values(gcp_platform_config)

        assert result["acme"]["server"] == "letsencrypt_test"

    def test_create_docker_registry_values_with_filesystem_storage(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_docker_registry_values(on_prem_platform_config)

        assert result == {
            "image": {"repository": "ghcr.io/neuro-inc/registry"},
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": "registry-standard",
                "size": "100Gi",
            },
            "secrets": {"haSharedSecret": mock.ANY},
            "storage": "filesystem",
            "configData": {"storage": {"delete": {"enabled": True}}},
            "podLabels": {"service": "docker-registry"},
            "priorityClassName": "platform-services",
        }
        assert result["secrets"]["haSharedSecret"]

    def test_create_docker_registry_values_with_s3_minio_storage(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        on_prem_platform_config = replace(
            on_prem_platform_config,
            registry=replace(
                on_prem_platform_config.registry,
                docker_registry_storage_driver=DockerRegistryStorageDriver.S3,
                docker_registry_s3_endpoint=URL("http://platform-minio:9000"),
                docker_registry_s3_region="minio",
                docker_registry_s3_bucket="job-images",
                docker_registry_s3_access_key="minio-access-key",
                docker_registry_s3_secret_key="minio-secret-key",
                docker_registry_s3_disable_redirect=True,
                docker_registry_s3_force_path_style=True,
            ),
        )
        result = factory.create_docker_registry_values(on_prem_platform_config)

        assert result == {
            "replicaCount": 2,
            "image": {"repository": "ghcr.io/neuro-inc/registry"},
            "ingress": {"enabled": False},
            "secrets": {
                "haSharedSecret": mock.ANY,
                "s3": {
                    "accessKey": "minio-access-key",
                    "secretKey": "minio-secret-key",
                },
            },
            "storage": "s3",
            "s3": {
                "region": "minio",
                "regionEndpoint": "platform-minio:9000",
                "bucket": "job-images",
            },
            "configData": {
                "storage": {
                    "delete": {"enabled": True},
                    "redirect": {"disable": True},
                    "s3": {"secure": False, "forcepathstyle": True},
                }
            },
            "podLabels": {"service": "docker-registry"},
            "priorityClassName": "platform-services",
        }
        assert result["secrets"]["haSharedSecret"]

    def test_create_harbor_values_with_filesystem_storage(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        on_prem_platform_config = replace(
            on_prem_platform_config,
            registry=replace(
                on_prem_platform_config.registry,
                docker_registry_type=DockerRegistryType.HARBOR,
            ),
        )
        result = factory.create_harbor_values(on_prem_platform_config)

        assert result == {
            "expose": {
                "tls": {"enabled": False},
                "ingress": {
                    "hosts": {
                        "core": "harbor.apps."
                        f"{on_prem_platform_config.ingress_dns_name}"
                    },
                    "className": "traefik",
                    "annotations": None,
                },
            },
            "persistence": {
                "persistentVolumeClaim": {
                    "registry": {
                        "storageClass": "registry-standard",
                        "size": "100Gi",
                    },
                },
                "imageChartStorage": {"type": "filesystem"},
            },
            "externalURL": f"harbor.apps.{on_prem_platform_config.ingress_dns_name}",
        }

    def test_create_harbor_values_with_s3_storage(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        on_prem_platform_config = replace(
            on_prem_platform_config,
            registry=replace(
                on_prem_platform_config.registry,
                docker_registry_type=DockerRegistryType.HARBOR,
                docker_registry_storage_driver=DockerRegistryStorageDriver.S3,
                docker_registry_s3_endpoint=URL("https://s3.amazonaws.com"),
                docker_registry_s3_region="us-east-1",
                docker_registry_s3_bucket="harbor-registry",
                docker_registry_s3_access_key="aws-access-key",
                docker_registry_s3_secret_key="aws-secret-key",
                docker_registry_s3_disable_redirect=False,
            ),
        )
        result = factory.create_harbor_values(on_prem_platform_config)

        assert result == {
            "expose": {
                "tls": {"enabled": False},
                "ingress": {
                    "hosts": {
                        "core": "harbor.apps."
                        f"{on_prem_platform_config.ingress_dns_name}"
                    },
                    "className": "traefik",
                    "annotations": None,
                },
            },
            "persistence": {
                "persistentVolumeClaim": {
                    "registry": {},
                },
                "imageChartStorage": {
                    "type": "s3",
                    "s3": {
                        "bucket": "harbor-registry",
                        "region": "us-east-1",
                        "regionendpoint": "s3.amazonaws.com",
                        "accesskey": "aws-access-key",
                        "secretkey": "aws-secret-key",
                        "secure": True,
                        "rootdirectory": "/harbor",
                    },
                    "disableredirect": False,
                },
            },
            "externalURL": f"harbor.apps.{on_prem_platform_config.ingress_dns_name}",
        }

    def test_create_harbor_values_with_admin_credentials(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        on_prem_platform_config = replace(
            on_prem_platform_config,
            registry=replace(
                on_prem_platform_config.registry,
                docker_registry_type=DockerRegistryType.HARBOR,
                docker_registry_username="admin",
                docker_registry_password="admin-password",
            ),
        )
        result = factory.create_harbor_values(on_prem_platform_config)

        assert (
            result["existingSecretAdminPassword"]
            == f"{on_prem_platform_config.release_name}-docker-registry"
        )
        assert result["existingSecretAdminPasswordKey"] == "password"

    def test_create_minio_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_minio_values(on_prem_platform_config)

        assert result == {
            "image": {
                "repository": "ghcr.io/neuro-inc/minio",
                "tag": "RELEASE.2022-03-08T22-28-51Z",
            },
            "imagePullSecrets": [
                {"name": "platform-docker-config"},
                {"name": "platform-docker-hub-config"},
            ],
            "DeploymentUpdate": {
                "type": "RollingUpdate",
                "maxUnavailable": 1,
                "maxSurge": 0,
            },
            "resources": {
                "requests": {
                    "cpu": "1",
                    "memory": "2Gi",
                }
            },
            "podLabels": {"service": "minio"},
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": "blob-storage-standard",
                "size": "10Gi",
            },
            "accessKey": "username",
            "secretKey": "password",
            "ingress": {"enabled": False},
            "priorityClassName": "platform-services",
        }

    def test_create_minio_gateway_values__gcp(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_minio_gateway_values(gcp_platform_config)

        assert gcp_platform_config.minio_gateway
        assert result == {
            "nameOverride": "minio-gateway",
            "fullnameOverride": "minio-gateway",
            "image": {"repository": "ghcr.io/neuro-inc/minio"},
            "imagePullSecrets": [
                {"name": "platform-docker-config"},
                {"name": "platform-docker-hub-config"},
            ],
            "replicaCount": 2,
            "env": [
                {
                    "name": "GOOGLE_APPLICATION_CREDENTIALS",
                    "value": "/etc/config/minio/gcs/key.json",
                }
            ],
            "rootUser": {
                "user": gcp_platform_config.minio_gateway.root_user,
                "password": gcp_platform_config.minio_gateway.root_user_password,
            },
            "secrets": [
                {
                    "data": {"key.json": "{}"},
                    "name": "minio-gateway-gcs-key",
                }
            ],
            "volumeMounts": [
                {
                    "name": "gcp-credentials",
                    "mountPath": "/etc/config/minio/gcs",
                    "readOnly": True,
                }
            ],
            "volumes": [
                {
                    "name": "gcp-credentials",
                    "secret": {
                        "secretName": "minio-gateway-gcs-key",
                        "optional": False,
                    },
                }
            ],
            "cloudStorage": {"type": "gcs", "gcs": {"project": "project"}},
            "securityContext": {
                "enabled": True,
                "runAsGroup": 1000,
                "runAsUser": 1000,
                "fsGroup": 1000,
            },
        }

    def test_create_minio_gateway_values__azure(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_minio_gateway_values(azure_platform_config)

        assert azure_platform_config.minio_gateway
        assert result == {
            "nameOverride": "minio-gateway",
            "fullnameOverride": "minio-gateway",
            "image": {"repository": "ghcr.io/neuro-inc/minio"},
            "imagePullSecrets": [
                {"name": "platform-docker-config"},
                {"name": "platform-docker-hub-config"},
            ],
            "replicaCount": 2,
            "rootUser": {
                "user": azure_platform_config.minio_gateway.root_user,
                "password": azure_platform_config.minio_gateway.root_user_password,
            },
            "cloudStorage": {"type": "azure"},
            "securityContext": {
                "enabled": True,
                "runAsGroup": 1000,
                "runAsUser": 1000,
                "fsGroup": 1000,
            },
        }

    def test_create_gcp_traefik_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(gcp_platform_config)

        assert result == {
            "nameOverride": "traefik",
            "fullnameOverride": "traefik",
            "instanceLabelOverride": "platform",
            "image": {"name": "ghcr.io/neuro-inc/traefik"},
            "deployment": {
                "replicas": 2,
                "labels": {
                    "service": "traefik",
                    "platform.apolo.us/component": "ingress-gateway",
                },
                "podLabels": {
                    "service": "traefik",
                    "platform.apolo.us/component": "ingress-gateway",
                },
                "imagePullSecrets": [
                    {"name": "platform-docker-config"},
                    {"name": "platform-docker-hub-config"},
                ],
            },
            "resources": {
                "requests": {"cpu": "250m", "memory": "256Mi"},
                "limits": {"cpu": "1000m", "memory": "1Gi"},
            },
            "service": {
                "type": "LoadBalancer",
                "annotations": {},
            },
            "ports": {
                "web": {"redirectTo": {"port": "websecure"}},
                "websecure": {"tls": {"enabled": True}},
            },
            "additionalArguments": [
                "--entryPoints.websecure.proxyProtocol.insecure=true",
                "--entryPoints.websecure.forwardedHeaders.insecure=true",
                "--entryPoints.websecure.http.middlewares="
                "platform-platform-cors@kubernetescrd",
                "--providers.kubernetesingress.ingressendpoint.ip=1.2.3.4",
            ],
            "providers": {
                "kubernetesCRD": {
                    "enabled": True,
                    "allowCrossNamespace": True,
                    "allowExternalNameServices": True,
                },
                "kubernetesIngress": {
                    "enabled": True,
                    "allowExternalNameServices": True,
                    "publishedService": {"enabled": False},
                },
            },
            "tlsStore": {
                "default": {
                    "defaultCertificate": {
                        "secretName": "platform-ssl-cert",
                    },
                },
            },
            "ingressClass": {"enabled": True},
            "ingressRoute": {"dashboard": {"enabled": False}},
            "logs": {"general": {"level": "ERROR"}},
            "priorityClassName": "platform-services",
            "metrics": {
                "prometheus": {
                    "service": {"enabled": True},
                    "serviceMonitor": {
                        "jobLabel": "app.kubernetes.io/name",
                        "additionalLabels": {
                            "platform.apolo.us/scrape-metrics": "true"
                        },
                    },
                }
            },
        }

    def test_create_gcp_traefik_values_with_ingress_load_balancer_source_ranges(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(
            replace(
                gcp_platform_config, ingress_load_balancer_source_ranges=["0.0.0.0/0"]
            )
        )

        assert result["service"]["loadBalancerSourceRanges"] == ["0.0.0.0/0"]

    def test_create_on_prem_traefik_values_with_custom_ports(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(
            replace(
                on_prem_platform_config,
                ingress_service_type=IngressServiceType.NODE_PORT,
                ingress_node_port_http=30080,
                ingress_node_port_https=30443,
                ingress_host_port_http=80,
                ingress_host_port_https=443,
            )
        )

        assert result["updateStrategy"] == {
            "rollingUpdate": {"maxSurge": 0, "maxUnavailable": 1}
        }
        assert result["service"]["type"] == "NodePort"
        assert result["ports"]["web"]["nodePort"] == 30080
        assert result["ports"]["web"]["hostPort"] == 80
        assert result["ports"]["websecure"]["nodePort"] == 30443
        assert result["ports"]["websecure"]["hostPort"] == 443

    def test_create_platform_storage_values__gcp(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-storage",
            "fullnameOverride": "platform-storage",
            "image": {"repository": "ghcr.io/neuro-inc/platformstorageapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_STORAGEAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "adminUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "storages": [{"type": "pvc", "path": "", "claimName": "platform-storage"}],
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "s3": {
                "endpoint": "http://minio-gateway:9000",
                "region": "us",
                "accessKeyId": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-storage-s3",
                            "key": "access_key_id",
                        }
                    }
                },
                "secretAccessKey": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-storage-s3",
                            "key": "secret_access_key",
                        }
                    }
                },
                "bucket": "job-metrics",
                "keyPrefix": "storage/",
            },
            "secrets": [
                {
                    "name": "platform-storage-s3",
                    "data": {
                        "access_key_id": "admin",
                        "secret_access_key": mock.ANY,
                    },
                }
            ],
            "storageUsageCollector": {
                "resources": {
                    "requests": {"cpu": "250m", "memory": "500Mi"},
                    "limits": {"cpu": "1000m", "memory": "1Gi"},
                }
            },
            "securityContext": {"enabled": True},
        }

    def test_create_platform_storage_values__aws(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(aws_platform_config)

        assert result["s3"] == {
            "region": "us-east-1",
            "bucket": "job-metrics",
            "keyPrefix": "storage/",
        }

    def test_create_platform_storage_values__azure(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(azure_platform_config)

        assert result["secrets"] == [
            {
                "name": "platform-storage-s3",
                "data": {
                    "access_key_id": "accountName2",
                    "secret_access_key": "accountKey2",
                },
            }
        ]
        assert result["s3"] == {
            "endpoint": "http://minio-gateway:9000",
            "accessKeyId": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "access_key_id",
                    }
                }
            },
            "secretAccessKey": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "secret_access_key",
                    }
                }
            },
            "region": "minio",
            "bucket": "job-metrics",
            "keyPrefix": "storage/",
        }

    def test_create_platform_storage_values__minio(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(on_prem_platform_config)

        assert result["secrets"] == [
            {
                "name": "platform-storage-s3",
                "data": {
                    "access_key_id": "username",
                    "secret_access_key": "password",
                },
            }
        ]
        assert result["s3"] == {
            "endpoint": "http://platform-minio:9000",
            "accessKeyId": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "access_key_id",
                    }
                }
            },
            "secretAccessKey": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "secret_access_key",
                    }
                }
            },
            "region": "minio",
            "bucket": "job-metrics",
            "keyPrefix": "storage/",
        }

    def test_create_platform_storage_values__emc_ecs(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.EMC_ECS,
                    emc_ecs_access_key_id="emc_ecs_access_key",
                    emc_ecs_secret_access_key="emc_ecs_secret_key",
                    emc_ecs_s3_endpoint=URL("https://emc-ecs.s3"),
                    emc_ecs_management_endpoint=URL("https://emc-ecs.management"),
                    emc_ecs_s3_assumable_role="s3-role",
                ),
            )
        )

        assert result["secrets"] == [
            {
                "name": "platform-storage-s3",
                "data": {
                    "access_key_id": "emc_ecs_access_key",
                    "secret_access_key": "emc_ecs_secret_key",
                },
            }
        ]
        assert result["s3"] == {
            "endpoint": "https://emc-ecs.s3",
            "region": "emc-ecs",
            "accessKeyId": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "access_key_id",
                    }
                }
            },
            "secretAccessKey": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "secret_access_key",
                    }
                }
            },
            "bucket": "job-metrics",
            "keyPrefix": "storage/",
        }

    def test_create_platform_storage_values__open_stack(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.OPEN_STACK,
                    open_stack_username="os_user",
                    open_stack_password="os_password",
                    open_stack_s3_endpoint=URL("https://os.s3"),
                    open_stack_endpoint=URL("https://os.management"),
                    open_stack_region_name="os_region",
                ),
            )
        )

        assert result["secrets"] == [
            {
                "name": "platform-storage-s3",
                "data": {
                    "access_key_id": "os_user",
                    "secret_access_key": "os_password",
                },
            }
        ]
        assert result["s3"] == {
            "endpoint": "https://os.s3",
            "accessKeyId": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "access_key_id",
                    }
                }
            },
            "secretAccessKey": {
                "valueFrom": {
                    "secretKeyRef": {
                        "name": "platform-storage-s3",
                        "key": "secret_access_key",
                    }
                }
            },
            "region": "os_region",
            "bucket": "job-metrics",
            "keyPrefix": "storage/",
        }

    def test_create_platform_storage_values__multiple_storages(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(
                gcp_platform_config,
                platform_spec=gcp_platform_config.platform_spec.model_copy(
                    update={
                        "platform_storage": PlatformStorageSpec(
                            helm_values=PlatformStorageSpec.HelmValues(
                                storages=[
                                    PlatformStorageSpec.HelmValues.Storage(
                                        path="/storage1"
                                    ),
                                    PlatformStorageSpec.HelmValues.Storage(
                                        path="/storage2"
                                    ),
                                ]
                            )
                        )
                    }
                ),
            )
        )

        assert result["storages"] == [
            {
                "type": "pvc",
                "path": "/storage1",
                "claimName": "platform-storage-storage1",
            },
            {
                "type": "pvc",
                "path": "/storage2",
                "claimName": "platform-storage-storage2",
            },
        ]

    def test_create_platform_storage_values__no_auth_url(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, auth_url=URL("-"), token="")

        result = factory.create_platform_storage_values(gcp_platform_config)

        assert result["platform"]["authUrl"] == "-"
        assert result["platform"]["token"] == {"value": ""}

    def test_create_platform_storage_values__no_tracing_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, sentry_dsn=None)

        result = factory.create_platform_storage_values(gcp_platform_config)

        assert "sentry" not in result

    def test_create_platform_storage_values__with_overrides(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        overrides: dict[str, Any] = {
            "helmValues": {
                "storages": [
                    {
                        "path": "/override",
                        "nfs": {"server": "server", "path": "/"},
                    }
                ],
                "extra": {"foo": "bar"},
            }
        }

        platform_storage = PlatformStorageSpec.model_validate(overrides)

        result = factory.create_platform_storage_values(
            replace(
                gcp_platform_config,
                platform_spec=gcp_platform_config.platform_spec.model_copy(
                    update={"platform_storage": platform_storage},
                ),
            )
        )

        assert result["storages"] == [
            {
                "type": "pvc",
                "path": "/override",
                "claimName": "platform-storage-override",
            }
        ]
        assert result["extra"] == overrides["helmValues"]["extra"]

    def test_create_aws_buckets_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_values(aws_platform_config)

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "aws",
                "aws": {"regionName": "us-east-1", "s3RoleArn": ""},
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{aws_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": aws_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_aws_buckets_values_without_cors(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_values(
            replace(aws_platform_config, ingress_cors_origins=[])
        )

        assert "cors" not in result

    def test_create_emc_ecs_buckets_values(
        self,
        on_prem_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_buckets_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.EMC_ECS,
                    emc_ecs_access_key_id="access_key",
                    emc_ecs_secret_access_key="secret_key",
                    emc_ecs_s3_endpoint=URL("https://emc-ecs.s3"),
                    emc_ecs_management_endpoint=URL("https://emc-ecs.management"),
                    emc_ecs_s3_assumable_role="s3-role",
                ),
            )
        )

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "emc_ecs",
                "emc_ecs": {
                    "accessKeyId": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "key",
                                "name": "platform-buckets-emc-ecs-key",
                            }
                        }
                    },
                    "managementEndpointUrl": "https://emc-ecs.management",
                    "s3EndpointUrl": "https://emc-ecs.s3",
                    "s3RoleUrn": "s3-role",
                    "secretAccessKey": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "secret",
                                "name": "platform-buckets-emc-ecs-key",
                            }
                        },
                    },
                },
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{on_prem_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": on_prem_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "data": {"key": "access_key", "secret": "secret_key"},
                    "name": "platform-buckets-emc-ecs-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_open_stack_buckets_values(
        self,
        on_prem_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_buckets_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.OPEN_STACK,
                    open_stack_username="account_id",
                    open_stack_password="password",
                    open_stack_s3_endpoint=URL("https://os.s3"),
                    open_stack_endpoint=URL("https://os.management"),
                    open_stack_region_name="region",
                ),
            ),
        )

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "open_stack",
                "open_stack": {
                    "accountId": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "accountId",
                                "name": "platform-buckets-open-stack-key",
                            }
                        }
                    },
                    "endpointUrl": "https://os.management",
                    "s3EndpointUrl": "https://os.s3",
                    "regionName": "region",
                    "password": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "password",
                                "name": "platform-buckets-open-stack-key",
                            }
                        },
                    },
                },
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{on_prem_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": on_prem_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "data": {"accountId": "account_id", "password": "password"},
                    "name": "platform-buckets-open-stack-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_on_prem_buckets_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_values(on_prem_platform_config)
        cluster_name = on_prem_platform_config.cluster_name

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "minio",
                "minio": {
                    "accessKeyId": "username",
                    "regionName": "minio",
                    "secretAccessKey": "password",
                    "url": "http://platform-minio:9000",
                    "publicUrl": f"https://blob.{cluster_name}.org.neu.ro",
                },
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_gcp_buckets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "gcp",
                "gcp": {
                    "SAKeyJsonB64": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "SAKeyB64",
                                "name": "platform-buckets-gcp-sa-key",
                            }
                        }
                    }
                },
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"SAKeyB64": "e30="}, "name": "platform-buckets-gcp-sa-key"},
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_azure_buckets_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_values(azure_platform_config)

        assert result == {
            "nameOverride": "platform-buckets",
            "fullnameOverride": "platform-buckets",
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "azure",
                "azure": {
                    "credential": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "key": "key",
                                "name": "platform-buckets-azure-storage-account-key",
                            }
                        }
                    },
                    "url": "https://accountName2.blob.core.windows.net",
                },
            },
            "image": {"repository": "ghcr.io/neuro-inc/platformbucketsapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_BUCKETS_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{azure_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": azure_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "data": {"key": "accountKey2"},
                    "name": "platform-buckets-azure-storage-account-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_gcp_platform_registry_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-registry",
            "fullnameOverride": "platform-registry",
            "image": {"repository": "ghcr.io/neuro-inc/platformregistryapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_REGISTRYAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"registry.{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": "platform-registry-gcp-key",
                    "data": {
                        "username": "_json_key",
                        "password": gcp_platform_config.gcp_service_account_key,
                    },
                },
            ],
            "upstreamRegistry": {
                "maxCatalogEntries": 10000,
                "project": "project",
                "tokenPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "password",
                            "name": "platform-registry-gcp-key",
                        }
                    }
                },
                "tokenService": "gcr.io",
                "tokenUrl": "https://gcr.io/v2/token",
                "tokenUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "username",
                            "name": "platform-registry-gcp-key",
                        }
                    }
                },
                "type": "oauth",
                "url": "https://gcr.io",
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_aws_platform_registry_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(aws_platform_config)

        assert result == {
            "nameOverride": "platform-registry",
            "fullnameOverride": "platform-registry",
            "image": {"repository": "ghcr.io/neuro-inc/platformregistryapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_REGISTRYAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"registry.{aws_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": aws_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [],
            "upstreamRegistry": {
                "url": "https://platform.dkr.ecr.us-east-1.amazonaws.com",
                "type": "aws_ecr",
                "region": "us-east-1",
                "maxCatalogEntries": 1000,
                "project": "neuro",
            },
            "sentry": mock.ANY,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_azure_platform_registry_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(azure_platform_config)

        assert result == {
            "nameOverride": "platform-registry",
            "fullnameOverride": "platform-registry",
            "image": {"repository": "ghcr.io/neuro-inc/platformregistryapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_REGISTRYAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"registry.{azure_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": azure_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": "platform-registry-azure-credentials",
                    "data": {
                        "username": azure_platform_config.registry.azure_username,
                        "password": azure_platform_config.registry.azure_password,
                    },
                },
            ],
            "upstreamRegistry": {
                "maxCatalogEntries": 10000,
                "project": "neuro",
                "tokenPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-registry-azure-credentials",
                            "key": "password",
                        }
                    }
                },
                "tokenService": "platform.azurecr.io",
                "tokenUrl": "https://platform.azurecr.io/oauth2/token",
                "tokenUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-registry-azure-credentials",
                            "key": "username",
                        }
                    }
                },
                "type": "oauth",
                "url": "https://platform.azurecr.io",
            },
            "sentry": mock.ANY,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_on_prem_platform_registry_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(on_prem_platform_config)

        assert result == {
            "nameOverride": "platform-registry",
            "fullnameOverride": "platform-registry",
            "image": {"repository": "ghcr.io/neuro-inc/platformregistryapi"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_REGISTRYAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [
                    f"registry.{on_prem_platform_config.cluster_name}.org.neu.ro"
                ],
            },
            "platform": {
                "clusterName": on_prem_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": "platform-docker-registry",
                    "data": {
                        "username": "",
                        "password": "",
                    },
                },
            ],
            "upstreamRegistry": {
                "type": "basic",
                "url": "http://platform-docker-registry:5000",
                "maxCatalogEntries": 10000,
                "project": "neuro",
                "basicUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-docker-registry",
                            "key": "username",
                        }
                    }
                },
                "basicPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-docker-registry",
                            "key": "password",
                        }
                    }
                },
            },
            "sentry": mock.ANY,
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_platform_monitoring_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-monitoring",
            "fullnameOverride": "platform-monitoring",
            "image": {"repository": "ghcr.io/neuro-inc/platformmonitoringapi"},
            "kubeletPort": 10250,
            "nvidiaDCGMPort": 9400,
            "jobsNamespace": "platform-jobs",
            "nodeLabels": {
                "nodePool": "platform.neuromation.io/nodepool",
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "apiUrl": "https://dev.neu.ro",
                "appsUrl": "https://dev.neu.ro",
                "authUrl": "https://dev.neu.ro",
                "configUrl": "https://dev.neu.ro",
                "registryUrl": (
                    f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
                ),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_MONITORINGAPI_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "fluentbit": {
                "image": {"repository": "ghcr.io/neuro-inc/fluent-bit"},
            },
            "logs": {
                "persistence": {
                    "type": "loki",
                    "loki": {
                        "endpoint": "http://loki-read.platform:3100",
                        "archiveDelay": "5",
                        "retentionPeriodS": "2592000",
                    },
                }
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_platform_monitoring_values__no_api_url(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, api_url=URL("-"), token="")

        result = factory.create_platform_monitoring_values(gcp_platform_config)

        assert result["platform"]["apiUrl"] == "-"
        assert result["platform"]["token"] == {"value": ""}

    def test_create_gcp_platform_container_runtime_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_container_runtime_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-container-runtime",
            "fullnameOverride": "platform-container-runtime",
            "image": {"repository": "ghcr.io/neuro-inc/platformcontainerruntime"},
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "platform.neuromation.io/job",
                                        "operator": "Exists",
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
        }

    def test_create_platform_secrets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-secrets",
            "fullnameOverride": "platform-secrets",
            "image": {"repository": "ghcr.io/neuro-inc/platformsecrets"},
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_SECRETS_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "secretsNamespace": "platform-jobs",
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "eventsUrl": "https://platform-events/apis/events",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_gcp_platform_reports_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(gcp_platform_config)

        assert result == {
            "nodePoolLabels": {
                "gpu": "platform.neuromation.io/accelerator",
                "job": "platform.neuromation.io/job",
                "nodePool": "platform.neuromation.io/nodepool",
                "preemptible": "platform.neuromation.io/preemptible",
            },
            "image": {"repository": "ghcr.io/neuro-inc/platform-reports"},
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "ingressAuthUrl": "https://platformingressauth",
                "configUrl": "https://dev.neu.ro",
                "apiUrl": "https://dev.neu.ro",
                "appsUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": "platform-reports-gcp-key",
                    "data": {"key.json": "{}"},
                },
            ],
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "platformJobs": {"namespace": "platform-jobs"},
            "metricsApi": {
                "ingress": {
                    "enabled": True,
                    "ingressClassName": "traefik",
                    "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
                }
            },
            "grafanaProxy": {
                "ingress": {
                    "enabled": True,
                    "ingressClassName": "traefik",
                    "hosts": [
                        f"grafana.{gcp_platform_config.cluster_name}.org.neu.ro",
                        f"metrics.{gcp_platform_config.cluster_name}.org.neu.ro",
                    ],
                    "annotations": {
                        "traefik.ingress.kubernetes.io/router.middlewares": (
                            "platform-platform-ingress-auth@kubernetescrd"
                        ),
                    },
                }
            },
            "prometheus": {
                "url": "http://thanos-query-http:10902",
                "remoteStorageEnabled": True,
            },
            "kube-prometheus-stack": {
                "global": {
                    "imageRegistry": "ghcr.io",
                    "imagePullSecrets": [
                        {"name": "platform-docker-config"},
                        {"name": "platform-docker-hub-config"},
                    ],
                },
                "prometheus": {
                    "ingress": {
                        "enabled": True,
                        "annotations": {
                            "traefik.ingress.kubernetes.io/router.middlewares": (
                                "platform-platform-federated-prometheus-auth@kubernetescrd"
                            ),
                            "traefik.ingress.kubernetes.io/router.priority": "1000",
                        },
                        "hosts": [
                            f"prometheus.{gcp_platform_config.cluster_name}.org.neu.ro",
                        ],
                        "ingressClassName": "traefik",
                        "paths": [
                            "/federate",
                        ],
                    },
                    "prometheusSpec": {
                        "image": {
                            "registry": "ghcr.io",
                            "repository": "neuro-inc/prometheus",
                        },
                        "thanos": {
                            "objectStorageConfig": {
                                "secret": {
                                    "type": "GCS",
                                    "config": {
                                        "bucket": "job-metrics",
                                        "service_account": "{}",
                                    },
                                }
                            },
                        },
                        "storageSpec": {
                            "volumeClaimTemplate": {
                                "spec": {
                                    "storageClassName": (
                                        "platform-standard-topology-aware"
                                    )
                                }
                            }
                        },
                        "externalLabels": {
                            "cluster": gcp_platform_config.cluster_name,
                        },
                        "priorityClassName": "platform-services",
                    },
                },
                "prometheusOperator": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/prometheus-operator",
                    },
                    "prometheusConfigReloader": {
                        "image": {
                            "registry": "ghcr.io",
                            "repository": "neuro-inc/prometheus-config-reloader",
                        }
                    },
                    "thanosImage": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/thanos",
                    },
                    "admissionWebhooks": {
                        "patch": {
                            "image": {
                                "registry": "ghcr.io",
                                "repository": "neuro-inc/kube-webhook-certgen",
                            },
                            "priorityClassName": "platform-services",
                        }
                    },
                    "kubeletService": {"namespace": "platform"},
                    "priorityClassName": "platform-services",
                },
                "kubelet": {"namespace": "platform"},
                "kubeStateMetrics": {"serviceMonitor": {"metricRelabelings": []}},
                "kube-state-metrics": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/kube-state-metrics",
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": "platform-docker-config"},
                            {"name": "platform-docker-hub-config"},
                        ]
                    },
                    "priorityClassName": "platform-services",
                    "rbac": {
                        "extraRules": [
                            {
                                "apiGroups": ["neuromation.io"],
                                "resources": ["platforms"],
                                "verbs": ["list", "watch"],
                            }
                        ]
                    },
                    "customResourceState": {
                        "enabled": True,
                        "config": {
                            "spec": {
                                "resources": [
                                    {
                                        "groupVersionKind": {
                                            "group": "neuromation.io",
                                            "version": "*",
                                            "kind": "Platform",
                                        },
                                        "labelsFromPath": {
                                            "name": ["metadata", "name"],
                                        },
                                        "metricNamePrefix": "kube_platform",
                                        "metrics": [
                                            {
                                                "name": "status_phase",
                                                "help": "Platform status phase",
                                                "each": {
                                                    "type": "StateSet",
                                                    "stateSet": {
                                                        "labelName": "phase",
                                                        "path": ["status", "phase"],
                                                        "list": [
                                                            "Pending",
                                                            "Deploying",
                                                            "Deleting",
                                                            "Deployed",
                                                            "Failed",
                                                        ],
                                                    },
                                                },
                                            }
                                        ],
                                    }
                                ]
                            }
                        },
                    },
                },
                "nodeExporter": {
                    "enabled": True,
                },
                "prometheus-node-exporter": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/node-exporter",
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": "platform-docker-config"},
                            {"name": "platform-docker-hub-config"},
                        ]
                    },
                },
                "alertmanager": {
                    "alertmanagerSpec": {
                        "image": {
                            "registry": "ghcr.io",
                            "repository": "neuro-inc/alertmanager",
                        },
                        "configSecret": "platform-alertmanager-config",
                        "secrets": ["platform-token"],
                    }
                },
            },
            "thanos": {
                "image": {"repository": "ghcr.io/neuro-inc/thanos"},
                "store": {
                    "persistentVolumeClaim": {
                        "spec": {"storageClassName": "platform-standard-topology-aware"}
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "fsGroup": 1001,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "runAsGroup": 1001,
                        "runAsNonRoot": True,
                        "runAsUser": 1001,
                    },
                },
                "compact": {
                    "persistentVolumeClaim": {
                        "spec": {"storageClassName": "platform-standard-topology-aware"}
                    },
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "fsGroup": 1001,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "runAsGroup": 1001,
                        "runAsNonRoot": True,
                        "runAsUser": 1001,
                    },
                },
                "objstore": {
                    "type": "GCS",
                    "config": {"bucket": "job-metrics", "service_account": "{}"},
                },
                "priorityClassName": "platform-services",
                "sidecar": {"selector": {"app": None}},
                "bucket": {
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "fsGroup": 1001,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "runAsGroup": 1001,
                        "runAsNonRoot": True,
                        "runAsUser": 1001,
                    },
                },
                "query": {
                    "securityContext": {
                        "allowPrivilegeEscalation": False,
                        "fsGroup": 1001,
                        "fsGroupChangePolicy": "OnRootMismatch",
                        "runAsGroup": 1001,
                        "runAsNonRoot": True,
                        "runAsUser": 1001,
                    },
                },
            },
            "cloudProvider": {
                "type": "gcp",
                "region": "us-central1",
                "serviceAccountSecret": {
                    "name": "platform-reports-gcp-key",
                    "key": "key.json",
                },
            },
            "grafana": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/grafana",
                    "pullSecrets": [
                        "platform-docker-config",
                        "platform-docker-hub-config",
                    ],
                },
                "initChownData": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/busybox",
                        "pullSecrets": [
                            "platform-docker-config",
                            "platform-docker-hub-config",
                        ],
                    }
                },
                "sidecar": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/k8s-sidecar",
                        "pullSecrets": [
                            "platform-docker-config",
                            "platform-docker-hub-config",
                        ],
                    }
                },
                "adminUser": "admin",
                "adminPassword": "grafana_password",
                "priorityClassName": "platform-services",
            },
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_aws_platform_reports_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(aws_platform_config)

        assert result["cloudProvider"] == {"type": "aws", "region": "us-east-1"}

    def test_create_azure_platform_reports_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(azure_platform_config)

        assert result["cloudProvider"] == {"type": "azure", "region": "westus"}

    def test_create_kube_prometheus_stack_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_kube_prometheus_stack_values(gcp_platform_config)

        assert result == {
            "global": {
                "imageRegistry": "ghcr.io",
                "imagePullSecrets": [
                    {"name": "platform-docker-config"},
                    {"name": "platform-docker-hub-config"},
                ],
            },
            "prometheus": {
                "ingress": {
                    "enabled": True,
                    "annotations": {
                        "traefik.ingress.kubernetes.io/router.middlewares": (
                            "platform-platform-federated-prometheus-auth@kubernetescrd"
                        ),
                        "traefik.ingress.kubernetes.io/router.priority": "1000",
                    },
                    "hosts": [
                        f"prometheus.{gcp_platform_config.cluster_name}.org.neu.ro",
                    ],
                    "ingressClassName": "traefik",
                    "paths": ["/federate"],
                },
                "prometheusSpec": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/prometheus",
                    },
                    "storageSpec": {
                        "volumeClaimTemplate": {
                            "spec": {
                                "storageClassName": ("platform-standard-topology-aware")
                            }
                        }
                    },
                    "externalLabels": {
                        "cluster": gcp_platform_config.cluster_name,
                    },
                    "priorityClassName": "platform-services",
                    "thanos": {
                        "objectStorageConfig": {
                            "secret": {
                                "config": {
                                    "bucket": "job-metrics",
                                    "service_account": "{}",
                                },
                                "type": "GCS",
                            },
                        },
                    },
                },
            },
            "prometheusOperator": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/prometheus-operator",
                },
                "prometheusConfigReloader": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/prometheus-config-reloader",
                    }
                },
                "thanosImage": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/thanos",
                },
                "admissionWebhooks": {
                    "patch": {
                        "image": {
                            "registry": "ghcr.io",
                            "repository": "neuro-inc/kube-webhook-certgen",
                        },
                        "priorityClassName": "platform-services",
                    }
                },
                "kubeletService": {"namespace": "platform"},
                "priorityClassName": "platform-services",
            },
            "kubelet": {"namespace": "platform"},
            "kubeStateMetrics": {"serviceMonitor": {"metricRelabelings": []}},
            "kube-state-metrics": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/kube-state-metrics",
                },
                "serviceAccount": {
                    "imagePullSecrets": [
                        {"name": "platform-docker-config"},
                        {"name": "platform-docker-hub-config"},
                    ]
                },
                "priorityClassName": "platform-services",
                "rbac": {
                    "extraRules": [
                        {
                            "apiGroups": ["neuromation.io"],
                            "resources": ["platforms"],
                            "verbs": ["list", "watch"],
                        }
                    ]
                },
                "customResourceState": {
                    "enabled": True,
                    "config": {
                        "spec": {
                            "resources": [
                                {
                                    "groupVersionKind": {
                                        "group": "neuromation.io",
                                        "version": "*",
                                        "kind": "Platform",
                                    },
                                    "labelsFromPath": {
                                        "name": ["metadata", "name"],
                                    },
                                    "metricNamePrefix": "kube_platform",
                                    "metrics": [
                                        {
                                            "name": "status_phase",
                                            "help": "Platform status phase",
                                            "each": {
                                                "type": "StateSet",
                                                "stateSet": {
                                                    "labelName": "phase",
                                                    "path": ["status", "phase"],
                                                    "list": [
                                                        "Pending",
                                                        "Deploying",
                                                        "Deleting",
                                                        "Deployed",
                                                        "Failed",
                                                    ],
                                                },
                                            },
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                },
            },
            "nodeExporter": {
                "enabled": True,
            },
            "prometheus-node-exporter": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/node-exporter",
                },
                "serviceAccount": {
                    "imagePullSecrets": [
                        {"name": "platform-docker-config"},
                        {"name": "platform-docker-hub-config"},
                    ]
                },
            },
            "alertmanager": {
                "alertmanagerSpec": {
                    "image": {
                        "registry": "ghcr.io",
                        "repository": "neuro-inc/alertmanager",
                    },
                    "configSecret": "platform-alertmanager-config",
                    "secrets": ["platform-token"],
                }
            },
        }

    def test_create_kube_prometheus_stack_values_with_k8s_label_relabelings(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_kube_prometheus_stack_values(gcp_platform_config)

        assert result["kubeStateMetrics"]["serviceMonitor"]["metricRelabelings"] == []

    def test_create_kube_prometheus_stack_values_with_platform_label_relabelings(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_kube_prometheus_stack_values(
            replace(
                gcp_platform_config,
                node_labels=LabelsConfig(
                    job="other.io/job",
                    node_pool="other.io/node-pool",
                    accelerator="other.io/accelerator",
                    preemptible="other.io/preemptible",
                ),
            )
        )

        assert result["kubeStateMetrics"]["serviceMonitor"]["metricRelabelings"] == [
            {
                "sourceLabels": ["label_other_io_job"],
                "targetLabel": "label_platform_neuromation_io_job",
            },
            {
                "sourceLabels": ["label_other_io_node_pool"],
                "targetLabel": "label_platform_neuromation_io_nodepool",
            },
            {
                "sourceLabels": ["label_other_io_accelerator"],
                "targetLabel": "label_platform_neuromation_io_accelerator",
            },
            {
                "sourceLabels": ["label_other_io_preemptible"],
                "targetLabel": "label_platform_neuromation_io_preemptible",
            },
        ]

    def test_create_thanos_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        updates = factory.create_thanos_values(gcp_platform_config)

        assert updates == {
            "image": {"repository": "ghcr.io/neuro-inc/thanos"},
            "store": {
                "persistentVolumeClaim": {
                    "spec": {"storageClassName": "platform-standard-topology-aware"}
                },
                "securityContext": {
                    "runAsUser": 1001,
                    "runAsGroup": 1001,
                    "fsGroup": 1001,
                    "runAsNonRoot": True,
                    "allowPrivilegeEscalation": False,
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
            },
            "query": {
                "securityContext": {
                    "runAsUser": 1001,
                    "runAsGroup": 1001,
                    "fsGroup": 1001,
                    "runAsNonRoot": True,
                    "allowPrivilegeEscalation": False,
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
            },
            "compact": {
                "persistentVolumeClaim": {
                    "spec": {"storageClassName": "platform-standard-topology-aware"}
                },
                "securityContext": {
                    "runAsUser": 1001,
                    "runAsGroup": 1001,
                    "fsGroup": 1001,
                    "runAsNonRoot": True,
                    "allowPrivilegeEscalation": False,
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
            },
            "bucket": {
                "securityContext": {
                    "runAsUser": 1001,
                    "runAsGroup": 1001,
                    "fsGroup": 1001,
                    "runAsNonRoot": True,
                    "allowPrivilegeEscalation": False,
                    "fsGroupChangePolicy": "OnRootMismatch",
                },
            },
            "objstore": {
                "type": "GCS",
                "config": {"bucket": "job-metrics", "service_account": "{}"},
            },
            "priorityClassName": "platform-services",
            "sidecar": {"selector": {"app": None}},
        }

    def test_create_thanos_values_for_aws(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_thanos_values(aws_platform_config)

        assert result["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "endpoint": "s3.us-east-1.amazonaws.com",
            },
        }

    def test_create_thanos_values_for_azure(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_thanos_values(azure_platform_config)

        assert result["objstore"] == {
            "type": "AZURE",
            "config": {
                "container": "job-metrics",
                "storage_account": "accountName2",
                "storage_account_key": "accountKey2",
            },
        }

    def test_create_thanos_values_for_minio(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_thanos_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.MINIO,
                    minio_public_url=URL("https://minio.org.neu.ro"),
                    minio_url=URL("http://platform-minio:9000"),
                    minio_region="minio",
                    minio_access_key="minio_access_key",
                    minio_secret_key="minio_secret_key",
                    minio_storage_class_name="blob-storage-standard",
                    minio_storage_size="10Gi",
                ),
            )
        )

        assert result["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "region": "minio",
                "endpoint": "platform-minio:9000",
                "access_key": "minio_access_key",
                "secret_key": "minio_secret_key",
                "insecure": True,
            },
        }

    def test_create_thanos_values_for_emc_ecs(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_thanos_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.EMC_ECS,
                    emc_ecs_access_key_id="emc_ecs_access_key",
                    emc_ecs_secret_access_key="emc_ecs_secret_key",
                    emc_ecs_s3_endpoint=URL("https://emc-ecs.s3"),
                    emc_ecs_management_endpoint=URL("https://emc-ecs.management"),
                    emc_ecs_s3_assumable_role="s3-role",
                ),
            )
        )

        assert result["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "endpoint": "emc-ecs.s3",
                "access_key": "emc_ecs_access_key",
                "secret_key": "emc_ecs_secret_key",
            },
        }

    def test_create_thanos_values_for_open_stack(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_thanos_values(
            replace(
                on_prem_platform_config,
                buckets=BucketsConfig(
                    provider=BucketsProvider.OPEN_STACK,
                    open_stack_username="os_user",
                    open_stack_password="os_password",
                    open_stack_s3_endpoint=URL("https://os.s3"),
                    open_stack_endpoint=URL("https://os.management"),
                    open_stack_region_name="os_region",
                ),
            )
        )

        assert result["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "region": "os_region",
                "endpoint": "os.s3",
                "access_key": "os_user",
                "secret_key": "os_password",
            },
        }

    def test_create_grafana_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_grafana_values(gcp_platform_config)

        assert result == {
            "image": {
                "registry": "ghcr.io",
                "repository": "neuro-inc/grafana",
                "pullSecrets": [
                    "platform-docker-config",
                    "platform-docker-hub-config",
                ],
            },
            "initChownData": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/busybox",
                    "pullSecrets": [
                        "platform-docker-config",
                        "platform-docker-hub-config",
                    ],
                }
            },
            "sidecar": {
                "image": {
                    "registry": "ghcr.io",
                    "repository": "neuro-inc/k8s-sidecar",
                    "pullSecrets": [
                        "platform-docker-config",
                        "platform-docker-hub-config",
                    ],
                }
            },
            "adminUser": "admin",
            "adminPassword": "grafana_password",
            "priorityClassName": "platform-services",
        }

    def test_create_platform_disks_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disks_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-disks",
            "fullnameOverride": "platform-disks",
            "image": {"repository": "ghcr.io/neuro-inc/platformdiskapi"},
            "disks": {
                "namespace": "platform-jobs",
                "limitPerUser": "10995116277760",
                "storageClassName": "platform-disk",
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {"key": "token", "name": "platform-token"}
                    }
                },
            },
            "service": {
                "annotations": {
                    "traefik.ingress.kubernetes.io/service.sticky.cookie": "true",
                    "traefik.ingress.kubernetes.io/service.sticky.cookie.name": (
                        "NEURO_DISK_API_SESSION"
                    ),
                }
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "securityContext": {"enabled": True},
        }

    def test_create_platform_disks_values_without_storage_class(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disks_values(
            replace(on_prem_platform_config, disks_storage_class_name=None)
        )

        assert "storageClassName" not in result["disks"]

    def test_create_on_prem_platform_disks_values_with_storage_class(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disks_values(
            replace(on_prem_platform_config, disks_storage_class_name="openebs-cstor")
        )

        assert result["disks"]["storageClassName"] == "openebs-cstor"

    def test_create_platform_api_poller_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_api_poller_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-api-poller",
            "fullnameOverride": "platform-api-poller",
            "image": {"repository": "ghcr.io/neuro-inc/platformapi"},
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "configUrl": "https://dev.neu.ro",
                "adminUrl": "https://dev.neu.ro/apis/admin/v1",
                "apiUrl": "https://dev.neu.ro/api/v1",
                "eventsUrl": "https://platform-events",
                "registryUrl": (
                    f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
                ),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        }
                    }
                },
            },
            "jobs": {
                "namespace": "platform-jobs",
                "ingressClass": "traefik",
                "ingressAuthMiddleware": (
                    "platform-platform-ingress-auth@kubernetescrd"
                ),
                "ingressErrorPageMiddleware": (
                    "platform-platform-error-page@kubernetescrd"
                ),
                "ingressOAuthAuthorizeUrl": (
                    "https://platformingressauth/oauth/authorize"
                ),
                "imagePullSecret": "platform-docker-hub-config",
            },
            "storages": [{"path": "", "type": "pvc", "claimName": "platform-storage"}],
            "nodeLabels": {
                "job": "platform.neuromation.io/job",
                "preemptible": "platform.neuromation.io/preemptible",
                "nodePool": "platform.neuromation.io/nodepool",
            },
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
        }

    def test_create_platform_api_poller_values_with_multiple_storages(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_api_poller_values(
            replace(
                gcp_platform_config,
                platform_spec=gcp_platform_config.platform_spec.model_copy(
                    update={
                        "platform_storage": PlatformStorageSpec(
                            helm_values=PlatformStorageSpec.HelmValues(
                                storages=[
                                    PlatformStorageSpec.HelmValues.Storage(
                                        path="/storage1"
                                    ),
                                    PlatformStorageSpec.HelmValues.Storage(
                                        path="/storage2"
                                    ),
                                ]
                            )
                        )
                    }
                ),
            )
        )

        assert result["storages"] == [
            {
                "type": "pvc",
                "path": "/storage1",
                "claimName": "platform-storage-storage1",
            },
            {
                "type": "pvc",
                "path": "/storage2",
                "claimName": "platform-storage-storage2",
            },
        ]

    def test_create_prometheus_external_cluster_label(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(gcp_platform_config)
        prom = result["kube-prometheus-stack"]["prometheus"]["prometheusSpec"]
        assert prom["externalLabels"]["cluster"]
        assert prom["externalLabels"]["cluster"] == gcp_platform_config.cluster_name

    def test_create_platform_metadata_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_metadata_values(gcp_platform_config)

        assert result == {
            "nameOverride": "platform-metadata",
            "fullnameOverride": "platform-metadata",
            "image": {"repository": "ghcr.io/neuro-inc/platform-metadata"},
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
            "priorityClassName": "platform-services",
            "platform": {
                "appsUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-token",
                        },
                    },
                },
            },
            "securityContext": {"enabled": True},
        }

    def test_create_cluster_secret_store(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        cluster_name = gcp_platform_config.cluster_name
        result = factory.create_cluster_secret_store(gcp_platform_config)

        assert result == {
            "vault": {
                "server": "https://vault.dev.apolo.us",
                "path": f"{cluster_name}--kv-v2",
                "version": "v2",
                "auth": {
                    "kubernetes": {
                        "mountPath": f"{cluster_name}--jwt",
                        "role": f"{cluster_name}--platform",
                    }
                },
            }
        }

    def test_create_external_secrets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_external_secrets_values(gcp_platform_config)

        assert result == {
            "nameOverride": "external-secrets",
            "fullnameOverride": "external-secrets",
            "installCRDs": True,
            "replicaCount": 1,
            "podLabels": {
                "service": "external-secrets",
                "platform.apolo.us/component": "external-secrets",
            },
        }

    def test_create_external_secrets_values__with_overrides(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        external_secrets = ExternalSecretsSpec.model_validate(
            {"helmValues": {"customField": "customValue"}}
        )

        result = factory.create_external_secrets_values(
            replace(
                gcp_platform_config,
                platform_spec=gcp_platform_config.platform_spec.model_copy(
                    update={"external_secrets": external_secrets},
                ),
            )
        )

        assert result == {
            "nameOverride": "external-secrets",
            "fullnameOverride": "external-secrets",
            "installCRDs": True,
            "replicaCount": 1,
            "podLabels": {
                "service": "external-secrets",
                "platform.apolo.us/component": "external-secrets",
            },
            "customField": "customValue",
        }

    def test_create_external_secret_objects(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_external_secret_objects(
            replace(
                gcp_platform_config,
                platform_spec=gcp_platform_config.platform_spec.model_copy(
                    update={
                        "external_secret_objects": ExternalSecretObjectsSpec(
                            root=[
                                ExternalSecretObjectsSpec.ExternalSecretObject(
                                    name="test-secret",
                                    data={
                                        "secret-key": ExternalSecretObjectsSpec.ExternalSecretObject.RemoteRef(  # noqa: E501
                                            key="remote-key",
                                            property="remote-property",
                                        )
                                    },
                                )
                            ]
                        )
                    }
                ),
            )
        )

        assert result == [
            {
                "name": "test-secret",
                "data": {
                    "secret-key": {
                        "key": "remote-key",
                        "property": "remote-property",
                    }
                },
            }
        ]
