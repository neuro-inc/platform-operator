from dataclasses import replace
from unittest import mock

import pytest

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import Config, LabelsConfig, PlatformConfig


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
                "labels": {"nodePool": "platform.neuromation.io/nodepool"},
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
            "nvidia-gpu-driver-gcp": mock.ANY,
            "platform-storage": mock.ANY,
            "platform-registry": mock.ANY,
            "platform-monitoring": mock.ANY,
            "platform-object-storage": mock.ANY,
            "platform-secrets": mock.ANY,
            "platform-reports": mock.ANY,
            "platform-disk-api": mock.ANY,
        }

    def test_create_gcp_platform_values_with_gcs_storage(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
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
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(aws_platform_config)

        assert "cluster-autoscaler" in result
        assert "nvidia-gpu-driver" in result

    def test_create_azure_platform_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
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
        assert "nvidia-gpu-driver" in result

    def test_create_on_prem_platform_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
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
        assert "nvidia-gpu-driver" in result
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
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_consul_values(gcp_platform_config)

        assert result == {
            "Replicas": 3,
            "StorageClass": "platform-standard-topology-aware",
        }

    def test_create_on_prem_consul_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_consul_values(on_prem_platform_config)

        assert result == {
            "Replicas": 1,
            "StorageClass": "standard",
        }

    def test_create_gcp_traefik_values(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_traefik_values(gcp_platform_config)

        assert result == {
            "replicas": 3,
            "deploymentStrategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
            },
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
            "resources": {
                "requests": {"cpu": "1200m", "memory": "5Gi"},
                "limits": {"cpu": "1200m", "memory": "5Gi"},
            },
            "timeouts": {"responding": {"idleTimeout": "660s"}},
        }

    def test_create_aws_traefik_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(aws_platform_config)

        assert result["timeouts"] == {"responding": {"idleTimeout": "660s"}}
        assert result["service"] == {
            "annotations": {
                (
                    "service.beta.kubernetes.io/"
                    "aws-load-balancer-connection-idle-timeout"
                ): "600"
            }
        }

    def test_create_azure_traefik_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(azure_platform_config)

        assert result["timeouts"] == {"responding": {"idleTimeout": "660s"}}
        assert result["service"] == {
            "annotations": {
                "service.beta.kubernetes.io/azure-load-balancer-tcp-idle-timeout": "10"
            }
        }

    def test_create_on_prem_traefik_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_traefik_values(on_prem_platform_config)

        assert result["replicas"] == 1
        assert result["serviceType"] == "NodePort"
        assert result["service"] == {"nodePorts": {"http": 30080, "https": 30443}}
        assert result["deployment"]["hostPort"] == {
            "httpEnabled": True,
            "httpsEnabled": True,
        }
        assert result["timeouts"] == {"responding": {"idleTimeout": "600s"}}

    def test_create_cluster_autoscaler_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(aws_platform_config)

        assert result == {
            "cloudProvider": "aws",
            "awsRegion": "us-east-1",
            "image": {
                "repository": "k8s.gcr.io/autoscaling/cluster-autoscaler",
                "tag": "v1.14.8",
            },
            "rbac": {"create": True},
            "autoDiscovery": {"clusterName": aws_platform_config.cluster_name},
            "extraArgs": {
                "expander": "least-waste",
                "skip-nodes-with-local-storage": False,
                "skip-nodes-with-system-pods": False,
                "balance-similar-node-groups": True,
            },
        }

    def test_create_cluster_autoscaler_not_supported(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        with pytest.raises(
            ValueError,
            match="Cluster autoscaler for Kubernetes 1.13.8 is not supported",
        ):
            factory.create_cluster_autoscaler_values(
                replace(aws_platform_config, kubernetes_version="1.13.8")
            )

    def test_create_cluster_autoscaler_for_kube_1_15(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(
            replace(aws_platform_config, kubernetes_version="1.15.3")
        )

        assert result["image"]["tag"] == "v1.15.7"

    def test_create_cluster_autoscaler_for_kube_1_16(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(
            replace(aws_platform_config, kubernetes_version="1.16.13")
        )

        assert result["image"]["tag"] == "v1.16.6"

    def test_create_cluster_autoscaler_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_cluster_autoscaler_values(
            replace(
                aws_platform_config,
                aws=replace(aws_platform_config.aws, role_arn="auto_scaling_role"),
            )
        )

        assert result["podAnnotations"] == {
            "iam.amazonaws.com/role": "auto_scaling_role"
        }

    def test_create_nvidia_gpu_driver_gcp_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_nvidia_gpu_driver_gcp_values(gcp_platform_config)

        assert result == {
            "gpuNodeLabel": gcp_platform_config.kubernetes_node_labels.accelerator
        }

    def test_create_nvidia_gpu_driver_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_nvidia_gpu_driver_values(aws_platform_config)

        assert result == {
            "gpuNodeLabel": aws_platform_config.kubernetes_node_labels.accelerator
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
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
        }

    def test_create_platform_storage_values_for_megafon_public(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(on_prem_platform_config, cluster_name="megafon-public")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
            ]
        )

    def test_create_platform_storage_values_for_megafon_poc(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(on_prem_platform_config, cluster_name="megafon-poc")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
                "https://master--megafon-neuro.netlify.app",
            ]
        )

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
                aws=replace(aws_platform_config.aws, role_arn="s3_role"),
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
                aws=replace(aws_platform_config.aws, role_arn="ecr_role"),
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
            "NP_MONITORING_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_MONITORING_K8S_NS": "platform-jobs",
            "NP_MONITORING_PLATFORM_API_URL": "https://dev.neu.ro/api/v1",
            "NP_MONITORING_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "NP_MONITORING_PLATFORM_CONFIG_URL": "https://dev.neu.ro/api/v1",
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
                aws=replace(aws_platform_config.aws, role_arn="s3_role"),
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

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
            ]
        )

    def test_create_platform_monitoring_values_for_megafon_poc(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
            replace(on_prem_platform_config, cluster_name="megafon-poc")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
                "https://master--megafon-neuro.netlify.app",
            ]
        )

    def test_create_platform_secrets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_SECRETS_K8S_NS": "platform-jobs",
            "NP_SECRETS_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
        }

    def test_create_platform_secrets_values_for_megafon_public(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(
            replace(on_prem_platform_config, cluster_name="megafon-public")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
            ]
        )

    def test_create_platform_secrets_values_for_megafon_poc(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(
            replace(on_prem_platform_config, cluster_name="megafon-poc")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
                "https://master--megafon-neuro.netlify.app",
            ]
        )

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
            "objectStore": {
                "supported": True,
                "configMapName": "thanos-object-storage-config",
            },
            "image": {"pullSecretName": "platform-docker-config"},
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "configUrl": "https://dev.neu.ro",
                "apiUrl": "https://dev.neu.ro/api/v1",
            },
            "platformJobs": {"namespace": "platform-jobs"},
            "grafanaProxy": {
                "ingress": {
                    "host": f"metrics.{gcp_platform_config.cluster_name}.org.neu.ro"
                }
            },
            "prometheus-operator": {
                "prometheus": {
                    "prometheusSpec": {
                        "thanos": {
                            "version": "v0.13.0",
                            "objectStorageConfig": {
                                "name": "thanos-object-storage-config",
                                "key": "thanos-object-storage.yaml",
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
                    }
                },
                "prometheusOperator": {"kubeletService": {"namespace": "platform"}},
                "kubelet": {"namespace": "platform"},
                "kubeStateMetrics": {
                    "serviceMonitor": {
                        "metricRelabelings": [
                            {
                                "sourceLabels": [
                                    "label_beta_kubernetes_io_instance_type"
                                ],
                                "targetLabel": "label_node_kubernetes_io_instance_type",
                            }
                        ]
                    }
                },
                "grafana": {"adminPassword": mock.ANY},
            },
            "thanos": {
                "store": {
                    "persistentVolumeClaim": {
                        "spec": {"storageClassName": "platform-standard-topology-aware"}
                    }
                },
                "compact": {
                    "persistentVolumeClaim": {
                        "spec": {"storageClassName": "platform-standard-topology-aware"}
                    }
                },
                "objstore": {
                    "type": "GCS",
                    "config": {"bucket": "job-metrics", "service_account": "{}"},
                },
            },
            "cloudProvider": {
                "type": "gcp",
                "region": "us-central1",
                "serviceAccountSecret": {
                    "name": "platform-gcp-service-account-key",
                    "key": "key.json",
                },
            },
        }

    def test_create_gcp_platform_reports_values_with_k8s_label_relabelings(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
            replace(gcp_platform_config, kubernetes_version="1.17.3")
        )

        assert (
            result["prometheus-operator"]["kubeStateMetrics"]["serviceMonitor"][
                "metricRelabelings"
            ]
            == []
        )

    def test_create_gcp_platform_reports_values_with_platform_label_relabelings(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
            replace(
                gcp_platform_config,
                kubernetes_node_labels=LabelsConfig(
                    job="other.io/job",
                    node_pool="other.io/node-pool",
                    accelerator="other.io/accelerator",
                    preemptible="other.io/preemptible",
                ),
            )
        )

        assert result["prometheus-operator"]["kubeStateMetrics"]["serviceMonitor"][
            "metricRelabelings"
        ] == [
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
            {
                "sourceLabels": ["label_beta_kubernetes_io_instance_type"],
                "targetLabel": "label_node_kubernetes_io_instance_type",
            },
        ]

    def test_create_aws_platform_reports_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(aws_platform_config)

        assert result["thanos"]["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "endpoint": "s3.us-east-1.amazonaws.com",
            },
        }
        assert result["cloudProvider"] == {"type": "aws", "region": "us-east-1"}

    def test_create_aws_platform_reports_values_with_roles(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
            replace(
                aws_platform_config,
                aws=replace(aws_platform_config.aws, role_arn="role_arn"),
            )
        )

        assert result["metricsServer"]["podMetadata"]["annotations"] == {
            "iam.amazonaws.com/role": "role_arn"
        }
        assert result["prometheus-operator"]["prometheus"]["prometheusSpec"][
            "podMetadata"
        ] == {"annotations": {"iam.amazonaws.com/role": "role_arn"}}
        assert result["thanos"]["store"]["annotations"] == {
            "iam.amazonaws.com/role": "role_arn"
        }
        assert result["thanos"]["bucket"]["annotations"] == {
            "iam.amazonaws.com/role": "role_arn"
        }
        assert result["thanos"]["compact"]["annotations"] == {
            "iam.amazonaws.com/role": "role_arn"
        }
        assert result["thanos"]["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "endpoint": "s3.us-east-1.amazonaws.com",
            },
        }
        assert result["cloudProvider"] == {"type": "aws", "region": "us-east-1"}

    def test_create_azure_platform_reports_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(azure_platform_config)

        assert result["thanos"]["objstore"] == {
            "type": "AZURE",
            "config": {
                "container": "job-metrics",
                "storage_account": "accountName2",
                "storage_account_key": "accountKey2",
            },
        }
        assert result["cloudProvider"] == {"type": "azure", "region": "westus"}

    def test_create_on_prem_platform_reports_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(on_prem_platform_config)

        assert result["objectStore"] == {"supported": False}
        assert result["prometheusProxy"] == {
            "prometheus": {"host": "prometheus-prometheus", "port": 9090}
        }
        assert (
            "thanos"
            not in result["prometheus-operator"]["prometheus"]["prometheusSpec"]
        )
        assert "cloudProvider" not in result

    def test_create_platform_disk_api_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_DISK_API_K8S_NS": "platform-jobs",
            "NP_DISK_API_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": "platform-docker-config",
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
            "NP_DISK_PROVIDER": "gcp",
        }

    def test_create_platform_disk_api_values_for_megafon_public(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(
            replace(on_prem_platform_config, cluster_name="megafon-public")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
            ]
        )

    def test_create_platform_disk_api_values_for_megafon_poc(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(
            replace(on_prem_platform_config, cluster_name="megafon-poc")
        )

        assert result["NP_CORS_ORIGINS"] == ",".join(
            [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
                "https://master--megafon-neuro.netlify.app",
            ]
        )

    def test_create_aws_platform_disk_api_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(aws_platform_config)

        assert result["NP_DISK_PROVIDER"] == "aws"

    def test_create_azure_platform_disk_api_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(azure_platform_config)

        assert result["NP_DISK_PROVIDER"] == "azure"

    def test_create_gcp_platform_disk_api_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(gcp_platform_config)

        assert result["NP_DISK_PROVIDER"] == "gcp"
