from dataclasses import replace
from unittest import mock

import pytest

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import Config, PlatformConfig


class TestHelmValuesFactory:
    @pytest.fixture
    def factory(self, config: Config) -> HelmValuesFactory:
        return HelmValuesFactory(config.helm_release_names, config.helm_chart_names)

    def test_create_gcp_platform_values_with_nfs_storage(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(gcp_platform_config)

        assert result == {
            "tags": {"gcp": True},
            "serviceToken": "token",
            "kubernetes": {
                "nodePools": [
                    {"name": "n1-highmem-8-name", "idleSize": 0, "cpu": 1.0, "gpu": 1}
                ],
                "imagesPrepull": {
                    "refreshInterval": "1h",
                    "images": [
                        {"image": "neuromation/base"},
                        {"image": "neuromation/web-shell"},
                    ],
                },
            },
            "gcp": {"serviceAccountKeyBase64": "e30="},
            "standardStorageClass": {
                "create": True,
                "name": "platform-standard-topology-aware",
            },
            "imagePullSecret": {
                "create": True,
                "name": "platform-docker-config",
                "credentials": {
                    "url": "https://neuro-docker-local-public.jfrog.io",
                    "email": f"{cluster_name}@neuromation.io",
                    "username": cluster_name,
                    "password": "password",
                },
            },
            "ingress": {
                "host": f"{cluster_name}.org.neu.ro",
                "jobFallbackHost": "default.jobs-dev.neu.ro",
                "registryHost": f"registry.{cluster_name}.org.neu.ro",
            },
            "jobs": {
                "namespace": {"create": True, "name": "platform-jobs"},
                "label": "platform.neuromation.io/job",
            },
            "storage": {"nfs": {"server": "192.168.0.3", "path": "/"}},
            "consul": mock.ANY,
            "traefik": mock.ANY,
            "platform-storage": mock.ANY,
            "platform-registry": mock.ANY,
            "ssh-auth": mock.ANY,
            "platform-monitoring": mock.ANY,
            "platform-object-storage": mock.ANY,
            "platform-secrets": mock.ANY,
        }

    def test_create_gcp_platform_values_with_gcs_storage(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                gcp=replace(
                    gcp_platform_config.gcp,
                    storage_type="gcs",
                    storage_gcs_bucket_name="platform-storage",
                ),
            )
        )

        assert result["storage"] == {"gcs": {"bucketName": "platform-storage"}}

    def test_create_aws_platform_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(aws_platform_config)

        assert "cluster-autoscaler" in result

    def test_create_azure_platform_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(azure_platform_config)

        assert result["registry"] == {
            "username": "admin",
            "password": "admin-password",
        }
        assert result["storage"] == {
            "azureFile": {
                "storageAccountName": "accountName1",
                "storageAccountKey": "accountKey1",
                "shareName": "share",
            }
        }
        assert result["blobStorage"] == {
            "azure": {
                "storageAccountName": "accountName2",
                "storageAccountKey": "accountKey2",
            }
        }

    def test_create_on_prem_platform_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(on_prem_platform_config)

        assert result["standardStorageClass"] == {"create": False, "name": "standard"}
        assert result["storage"] == {
            "nfs": {
                "server": "platform-nfs-server.platform.svc.cluster.local",
                "path": "/",
            }
        }
        assert "docker-registry" in result
        assert "minio" in result
        assert "platform-object-storage" not in result

    def test_create_docker_registry_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_docker_registry_values(on_prem_platform_config)

        assert result == {
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": "registry-standard",
                "size": "100Gi",
            },
            "secrets": {
                "haSharedSecret": (
                    f"{on_prem_platform_config.docker_registry.username}:"
                    f"{on_prem_platform_config.docker_registry.password}"
                )
            },
        }

    def test_create_nfs_server_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_nfs_server_values(on_prem_platform_config)

        assert result == {
            "rbac": {"create": True},
            "persistence": {
                "enabled": True,
                "storageClass": "storage-standard",
                "size": "1000Gi",
            },
        }

    def test_create_minio_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_minio_values(on_prem_platform_config)

        assert result == {
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": "blob-storage-standard",
                "size": "10Gi",
            },
            "accessKey": "minio_access_key",
            "secretKey": "minio_secret_key",
            "environment": {"MINIO_REGION_NAME": "minio"},
        }

    def test_create_obs_csi_driver_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_obs_csi_driver_values(gcp_platform_config)

        assert result == {
            "driverName": "obs.csi.neu.ro",
            "credentialsSecret": {
                "create": True,
                "gcpServiceAccountKeyBase64": "e30=",
            },
            "imagePullSecret": {
                "create": True,
                "credentials": {
                    "url": "https://neuro-docker-local-public.jfrog.io",
                    "email": f"{gcp_platform_config.cluster_name}@neuromation.io",
                    "username": gcp_platform_config.cluster_name,
                    "password": "password",
                },
            },
        }

    def test_create_consul_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_consul_values(gcp_platform_config)

        assert result == {
            "Replicas": 3,
            "StorageClass": "platform-standard-topology-aware",
        }

    def test_create_on_prem_consul_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_consul_values(on_prem_platform_config)

        assert result == {
            "Replicas": 1,
            "StorageClass": "standard",
        }

    def test_create_traefik_values(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_traefik_values(gcp_platform_config)

        assert result == {
            "replicas": 4,
            "imageTag": "1.7.20-alpine",
            "logLevel": "debug",
            "serviceType": "LoadBalancer",
            "externalTrafficPolicy": "Cluster",
            "ssl": {
                "enabled": True,
                "enforced": True,
                "defaultCert": "",
                "defaultKey": "",
            },
            "acme": {
                "enabled": True,
                "onHostRule": False,
                "staging": True,
                "persistence": {"enabled": False},
                "keyType": "RSA4096",
                "challengeType": "dns-01",
                "dnsProvider": {
                    "name": "exec",
                    "exec": {"EXEC_PATH": "/dns-01/resolve_dns_challenge.sh"},
                },
                "logging": True,
                "email": f"{cluster_name}@neuromation.io",
                "domains": {
                    "enabled": True,
                    "domainsList": [
                        {"main": f"{cluster_name}.org.neu.ro"},
                        {
                            "sans": [
                                f"*.{cluster_name}.org.neu.ro",
                                f"*.jobs.{cluster_name}.org.neu.ro",
                            ]
                        },
                    ],
                },
            },
            "kvprovider": {
                "consul": {
                    "watch": True,
                    "endpoint": "platform-consul:8500",
                    "prefix": "traefik",
                },
                "storeAcme": True,
                "acmeStorageLocation": "traefik/acme/account",
            },
            "kubernetes": {
                "ingressClass": "traefik",
                "namespaces": ["platform", "platform-jobs"],
            },
            "rbac": {"enabled": True},
            "deployment": {
                "labels": {"platform.neuromation.io/app": "ingress"},
                "podLabels": {"platform.neuromation.io/app": "ingress"},
            },
            "extraVolumes": [
                {
                    "name": "resolve-dns-challenge-script",
                    "configMap": {
                        "name": "platform-resolve-dns-challenge-script",
                        "defaultMode": 511,
                        "items": [
                            {
                                "key": "resolve_dns_challenge.sh",
                                "path": "resolve_dns_challenge.sh",
                            }
                        ],
                    },
                }
            ],
            "extraVolumeMounts": [
                {"name": "resolve-dns-challenge-script", "mountPath": "/dns-01"}
            ],
            "env": [
                {"name": "NP_PLATFORM_API_URL", "value": "https://dev.neu.ro/api/v1"},
                {"name": "NP_CLUSTER_NAME", "value": cluster_name},
                {
                    "name": "NP_CLUSTER_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platformservices-secret",
                            "key": "cluster_token",
                        }
                    },
                },
            ],
        }

    def test_create_aws_traefik_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_traefik_values(aws_platform_config)

        assert result["service"] == {
            "annotations": {
                (
                    "service.beta.kubernetes.io/"
                    "aws-load-balancer-connection-idle-timeout"
                ): "3600"
            }
        }

    def test_create_on_prem_traefik_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_traefik_values(on_prem_platform_config)

        assert result["replicas"] == 1
        assert result["serviceType"] == "NodePort"
        assert result["service"] == {"nodePorts": {"http": 30080, "https": 30443}}
        assert result["deployment"]["hostPort"] == {
            "httpEnabled": True,
            "httpsEnabled": True,
        }
        assert result["deploymentStrategy"] == {
            "type": "RollingUpdate",
            "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
        }

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

    def test_create_gcp_platform_monitoring_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_MONITORING_K8S_NS": "platform-jobs",
            "NP_MONITORING_PLATFORM_API_URL": "https://dev.neu.ro/api/v1",
            "NP_MONITORING_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "NP_MONITORING_REGISTRY_URL": (
                f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
            ),
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "fluentd": {
                "persistence": {
                    "enabled": True,
                    "storageClassName": "platform-standard-topology-aware",
                }
            },
            "logs": {
                "persistence": {
                    "type": "gcp",
                    "gcp": {
                        "bucket": "job-logs",
                        "project": "project",
                        "region": "us-central1",
                        "serviceAccountKeyBase64": "e30=",
                    },
                }
            },
        }

    def test_create_aws_platform_monitoring_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(aws_platform_config)

        assert result["logs"] == {
            "persistence": {
                "type": "aws",
                "aws": {"bucket": "job-logs", "region": "us-east-1"},
            },
        }

    def test_create_aws_platform_monitoring_values_with_roles(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
            replace(
                aws_platform_config,
                aws=replace(aws_platform_config.aws, role_s3_arn="s3_role"),
            )
        )

        assert result["monitoring"] == {
            "podAnnotations": {"iam.amazonaws.com/role": "s3_role"}
        }
        assert result["fluentd"]["podAnnotations"] == {
            "iam.amazonaws.com/role": "s3_role"
        }

    def test_create_azure_platform_monitoring_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(azure_platform_config)

        assert result["logs"] == {
            "persistence": {
                "type": "azure",
                "azure": {
                    "bucket": "job-logs",
                    "region": "westus",
                    "storageAccountKey": "accountKey2",
                    "storageAccountName": "accountName2",
                },
            },
        }

    def test_create_on_prem_platform_monitoring_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(on_prem_platform_config)

        assert result["NP_MONITORING_K8S_KUBELET_PORT"] == 10250
        assert result["logs"] == {
            "persistence": {
                "type": "minio",
                "minio": {
                    "url": "http://platform-minio:9000",
                    "accessKey": "minio_access_key",
                    "secretKey": "minio_secret_key",
                    "region": "minio",
                    "bucket": "job-logs",
                },
            },
        }

    def test_create_platform_monitoring_values_for_megafon_public(
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

    def test_create_platform_monitoring_values_for_megafon_poc(
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

    def test_create_platform_secrets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_SECRETS_K8S_NS": "platform-jobs",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
        }
