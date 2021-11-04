from dataclasses import replace
from unittest import mock

import pytest
from yarl import URL

from platform_operator.helm_values import HelmValuesFactory
from platform_operator.models import (
    BucketsConfig,
    BucketsProvider,
    Config,
    DockerConfig,
    LabelsConfig,
    MetricsStorageType,
    MonitoringConfig,
    PlatformConfig,
    StorageConfig,
    StorageType,
)


class TestHelmValuesFactory:
    @pytest.fixture
    def factory(self, config: Config) -> HelmValuesFactory:
        return HelmValuesFactory(
            config.helm_release_names,
            config.helm_chart_names,
            container_runtime="docker",
        )

    def test_create_gcp_platform_values_with_nfs_storage(
        self,
        cluster_name: str,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_values(gcp_platform_config)

        assert result == {
            "kubernetesProvider": "gcp",
            "traefikEnabled": True,
            "consulEnabled": False,
            "alpineImage": {"repository": "neuro.io/alpine"},
            "pauseImage": {"repository": "neuro.io/google_containers/pause"},
            "crictlImage": {"repository": "neuro.io/crictl"},
            "serviceToken": "token",
            "nodePools": [
                {"name": "n1-highmem-8", "idleSize": 0, "cpu": 1.0, "gpu": 1}
            ],
            "nodeLabels": {
                "nodePool": "platform.neuromation.io/nodepool",
                "job": "platform.neuromation.io/job",
                "gpu": "platform.neuromation.io/accelerator",
            },
            "nvidiaGpuDriver": {
                "image": {"repository": "neuro.io/nvidia/k8s-device-plugin"},
            },
            "imagesPrepull": {
                "refreshInterval": "1h",
                "images": [{"image": "neuromation/base"}],
            },
            "dockerConfigSecret": {
                "create": True,
                "name": "platform-docker-config",
                "credentials": {
                    "url": "https://neuro.io",
                    "email": f"{cluster_name}@neuromation.io",
                    "username": cluster_name,
                    "password": "password",
                },
            },
            "dockerHubConfigSecret": {
                "create": True,
                "name": "platform-docker-hub-config",
                "credentials": {
                    "url": "https://index.docker.io/v1/",
                    "email": f"{cluster_name}@neuromation.io",
                    "username": cluster_name,
                    "password": "password",
                },
            },
            "ingress": {
                "jobFallbackHost": "default.jobs-dev.neu.ro",
                "registryHost": f"registry.{cluster_name}.org.neu.ro",
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
                    "imagePullSecrets": [],
                    "resources": {"cpu": "1000m", "memory": "1024Mi"},
                    "env": {},
                    "nodeSelector": {},
                }
            ],
            "disks": {"storageClass": {"create": True, "name": "platform-disk"}},
            "storages": [
                {
                    "type": "nfs",
                    "path": "",
                    "size": "10Gi",
                    "nfs": {"server": "192.168.0.3", "path": "/"},
                }
            ],
            "traefik": mock.ANY,
            "platform-storage": mock.ANY,
            "platform-registry": mock.ANY,
            "platform-monitoring": mock.ANY,
            "platform-container-runtime": mock.ANY,
            "platform-secrets": mock.ANY,
            "platform-reports": mock.ANY,
            "platform-disk-api": mock.ANY,
            "platform-api-poller": mock.ANY,
            "platform-buckets-api": mock.ANY,
        }

    def test_create_gcp_platform_values_idle_jobs(
        self,
        gcp_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        gcp_platform_config = replace(
            gcp_platform_config,
            idle_jobs=[
                {
                    "name": "miner",
                    "count": 1,
                    "image": "miner",
                    "image_pull_secret": "secret",
                    "resources": {
                        "cpu_m": 1000,
                        "memory_mb": 1024,
                        "gpu": 1,
                    },
                    "env": {"NAME": "VALUE"},
                    "node_selector": {"gpu": "nvidia-tesla-k80"},
                }
            ],
        )

        result = factory.create_platform_values(gcp_platform_config)

        assert result["idleJobs"] == [
            {
                "name": "miner",
                "count": 1,
                "image": "miner",
                "imagePullSecrets": [{"name": "secret"}],
                "resources": {"cpu": "1000m", "memory": "1024Mi", "nvidia.com/gpu": 1},
                "env": {"NAME": "VALUE"},
                "nodeSelector": {"gpu": "nvidia-tesla-k80"},
            }
        ]

    def test_create_gcp_platform_values_with_consul(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(gcp_platform_config, consul_install=True)
        )

        assert result["consul"]

    def test_create_gcp_platform_values_with_kubernetes_storage(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        storage_class_name="storage-class",
                        storage_size="100Gi",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "kubernetes",
                "path": "",
                "storageClassName": "storage-class",
                "size": "100Gi",
            }
        ]

    def test_create_gcp_platform_values_with_gcs_storage(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.GCS,
                        gcs_bucket_name="platform-storage",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "gcs",
                "path": "",
                "size": "10Gi",
                "gcs": {"bucketName": "platform-storage"},
            }
        ]

    def test_create_gcp_platform_values_without_namespace(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(gcp_platform_config, jobs_namespace_create=False)
        )

        assert result["jobs"]["namespace"] == {
            "create": False,
            "name": gcp_platform_config.jobs_namespace,
        }

    def test_create_gcp_platform_values_without_docker_config_secret(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                docker_config=DockerConfig(
                    url=URL("https://neuro.io"),
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

    def test_create_aws_platform_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        assert factory.create_platform_values(aws_platform_config)

    def test_create_aws_platform_values_with_kubernetes_storage(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                aws_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        storage_class_name="storage-class",
                        storage_size="100Gi",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "kubernetes",
                "path": "",
                "size": "100Gi",
                "storageClassName": "storage-class",
            }
        ]

    def test_create_azure_platform_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(azure_platform_config)

        assert result["storages"] == [
            {
                "type": "azureFile",
                "path": "",
                "size": "10Gi",
                "azureFile": {
                    "storageAccountName": "accountName1",
                    "storageAccountKey": "accountKey1",
                    "shareName": "share",
                },
            }
        ]

    def test_create_azure_platform_values_with_kubernetes_storage(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                azure_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        storage_class_name="storage-class",
                        storage_size="100Gi",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "kubernetes",
                "path": "",
                "size": "100Gi",
                "storageClassName": "storage-class",
            }
        ]

    def test_create_azure_platform_values_with_nfs_storage(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                azure_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.NFS,
                        nfs_server="nfs-server",
                        nfs_export_path="/path",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "nfs",
                "path": "",
                "size": "10Gi",
                "nfs": {"server": "nfs-server", "path": "/path"},
            }
        ]

    def test_create_on_prem_platform_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(on_prem_platform_config)

        assert result["storages"] == [
            {
                "type": "kubernetes",
                "path": "",
                "storageClassName": "storage-standard",
                "size": "1000Gi",
            }
        ]
        assert result["dockerRegistryEnabled"] is True
        assert "docker-registry" in result
        assert result["minioEnabled"] is True
        assert "minio" in result
        assert "platform-object-storage" not in result

    def test_create_gcp_platform_values_with_smb_storage(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                gcp_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.SMB,
                        smb_server="smb-server",
                        smb_share_name="smb-share",
                        smb_username="smb-username",
                        smb_password="smb-password",
                    )
                ],
            )
        )

        assert result["storages"] == [
            {
                "type": "smb",
                "path": "",
                "size": "10Gi",
                "smb": {
                    "server": "smb-server",
                    "shareName": "smb-share",
                    "username": "smb-username",
                    "password": "smb-password",
                },
            }
        ]

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

        assert "dockerRegistryEnabled" not in result
        assert "docker-registry" not in result

    def test_create_on_prem_platform_values_without_minio(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(
            replace(
                on_prem_platform_config,
                buckets=replace(on_prem_platform_config.buckets, minio_install=False),
            )
        )

        assert "minioEnabled" not in result
        assert "minio" not in result

    def test_create_vcd_platform_values(
        self, vcd_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_values(vcd_platform_config)

        assert result["kubernetesProvider"] == "kubeadm"

    def test_create_docker_registry_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_docker_registry_values(on_prem_platform_config)

        assert result == {
            "image": {"repository": "neuro.io/registry"},
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": "registry-standard",
                "size": "100Gi",
            },
            "secrets": {"haSharedSecret": mock.ANY},
            "configData": {"storage": {"delete": {"enabled": True}}},
        }
        assert result["secrets"]["haSharedSecret"]

    def test_create_minio_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_minio_values(on_prem_platform_config)

        assert result == {
            "image": {
                "repository": "neuro.io/minio/minio",
                "tag": "RELEASE.2021-08-25T00-41-18Z",
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
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": "blob-storage-standard",
                "size": "10Gi",
            },
            "accessKey": "username",
            "secretKey": "password",
            "environment": {"MINIO_REGION_NAME": "minio"},
            "ingress": {
                "enabled": True,
                "annotations": {
                    "kubernetes.io/ingress.class": "traefik",
                    "traefik.frontend.rule.type": "PathPrefix",
                },
                "hosts": [f"blob.{on_prem_platform_config.cluster_name}.org.neu.ro"],
            },
        }

    def test_create_obs_csi_driver_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_obs_csi_driver_values(gcp_platform_config)

        assert result == {
            "image": "neuro.io/obs-csi-driver",
            "driverName": "obs.csi.neu.ro",
            "credentialsSecret": {
                "create": True,
                "gcpServiceAccountKeyBase64": "e30=",
            },
            "imagePullSecret": {
                "create": True,
                "credentials": {
                    "url": "https://neuro.io",
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
            "Image": "neuro.io/consul",
            "Replicas": 3,
            "StorageClass": "platform-standard-topology-aware",
        }

    def test_create_on_prem_consul_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_consul_values(on_prem_platform_config)

        assert result == {
            "Image": "neuro.io/consul",
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
            "image": "neuro.io/traefik",
            "imageTag": "1.7.20-alpine",
            "imagePullSecrets": [
                "platform-docker-config",
                "platform-docker-hub-config",
            ],
            "logLevel": "debug",
            "serviceType": "LoadBalancer",
            "externalTrafficPolicy": "Cluster",
            "ssl": {"enabled": True, "enforced": True},
            "acme": {
                "enabled": True,
                "onHostRule": False,
                "staging": True,
                "persistence": {"enabled": False},
                "keyType": "RSA4096",
                "challengeType": "dns-01",
                "dnsProvider": {
                    "name": "exec",
                    "exec": {
                        "EXEC_PATH": "/dns-01/challenge/resolve_dns_challenge.sh",
                    },
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
                    "endpoint": "http://consul:8500",
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
                    "name": "dns-challenge",
                    "configMap": {
                        "name": "platform-dns-challenge",
                        "defaultMode": 0o777,
                    },
                },
                {
                    "name": "dns-challenge-secret",
                    "secret": {"secretName": "platform-dns-challenge"},
                },
            ],
            "extraVolumeMounts": [
                {"name": "dns-challenge", "mountPath": "/dns-01/challenge"},
                {"name": "dns-challenge-secret", "mountPath": "/dns-01/secret"},
            ],
            "env": [
                {"name": "NP_PLATFORM_CONFIG_URL", "value": "https://dev.neu.ro"},
                {"name": "NP_CLUSTER_NAME", "value": cluster_name},
                {
                    "name": "NP_DNS_CHALLENGE_SCRIPT_NAME",
                    "value": "resolve_dns_challenge.sh",
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

    def test_create_platform_storage_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(gcp_platform_config)

        assert result == {
            "image": {"repository": "neuro.io/platformstorageapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-storage-token",
                            "key": "token",
                        }
                    }
                },
            },
            "storages": [{"type": "pvc", "path": "", "claimName": "platform-storage"}],
            "secrets": [{"name": "platform-storage-token", "data": {"token": "token"}}],
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
        }

    def test_create_platform_storage_values_with_multiple_storages(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_storage_values(
            replace(
                gcp_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        path="/storage1",
                        storage_class_name="class",
                    ),
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        path="/storage2",
                        storage_class_name="class",
                    ),
                ],
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

    def test_create_platform_storage_without_tracing_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, sentry_dsn=URL(""))

        result = factory.create_platform_storage_values(gcp_platform_config)

        assert "sentry" not in result

    def test_create_platform_storage_without_tracing_sample_rate_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        gcp_platform_config = replace(gcp_platform_config, sentry_sample_rate=None)

        result = factory.create_platform_storage_values(gcp_platform_config)

        assert result["sentry"] == {
            "dsn": "https://sentry",
            "clusterName": gcp_platform_config.cluster_name,
        }

    def test_create_aws_buckets_api_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(aws_platform_config)

        assert result == {
            "bucketNamespace": "platform-jobs",
            "bucketProvider": {
                "type": "aws",
                "aws": {"regionName": "us-east-1", "s3RoleArn": ""},
            },
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{aws_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": aws_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"}
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_aws_buckets_api_values_without_cors(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(
            replace(aws_platform_config, ingress_cors_origins=[])
        )

        assert "cors" not in result

    def test_create_aws_platform_buckets_api_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(
            replace(aws_platform_config, aws_role_arn="s3_role")
        )

        assert result["annotations"] == {"iam.amazonaws.com/role": "s3_role"}

    def test_create_emc_ecs_buckets_api_values(
        self,
        on_prem_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_buckets_api_values(
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
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{on_prem_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": on_prem_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"},
                {
                    "data": {"key": "access_key", "secret": "secret_key"},
                    "name": "platform-buckets-emc-ecs-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_open_stack_buckets_api_values(
        self,
        on_prem_platform_config: PlatformConfig,
        factory: HelmValuesFactory,
    ) -> None:
        result = factory.create_platform_buckets_api_values(
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
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{on_prem_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": on_prem_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"},
                {
                    "data": {"accountId": "account_id", "password": "password"},
                    "name": "platform-buckets-open-stack-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_on_prem_buckets_api_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(on_prem_platform_config)
        cluster_name = on_prem_platform_config.cluster_name

        assert result == {
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
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"}
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_gcp_buckets_api_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(gcp_platform_config)

        assert result == {
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
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"},
                {"data": {"SAKeyB64": "e30="}, "name": "platform-buckets-gcp-sa-key"},
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_azure_buckets_api_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_buckets_api_values(azure_platform_config)

        assert result == {
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
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "image": {"repository": "neuro.io/platformbucketsapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{azure_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "clusterName": azure_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-buckets-api-token",
                        }
                    }
                },
            },
            "secrets": [
                {"data": {"token": "token"}, "name": "platform-buckets-api-token"},
                {
                    "data": {"key": "accountKey2"},
                    "name": "platform-buckets-azure-storage-account-key",
                },
            ],
            "sentry": mock.ANY,
            "disableCreation": False,
        }

    def test_create_gcp_platform_registry_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "image": {"repository": "neuro.io/platformregistryapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"registry.{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-registry-token",
                            "key": "token",
                        }
                    }
                }
            },
            "secrets": [
                {
                    "name": "platform-registry-token",
                    "data": {"token": gcp_platform_config.token},
                },
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
        }

    def test_create_aws_platform_registry_values(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(aws_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": aws_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "AWS_DEFAULT_REGION": "us-east-1",
            "image": {"repository": "neuro.io/platformregistryapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"registry.{aws_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-registry-token",
                            "key": "token",
                        }
                    }
                }
            },
            "secrets": [
                {
                    "name": "platform-registry-token",
                    "data": {"token": aws_platform_config.token},
                }
            ],
            "upstreamRegistry": {
                "url": "https://platform.dkr.ecr.us-east-1.amazonaws.com",
                "type": "aws_ecr",
                "maxCatalogEntries": 1000,
                "project": "neuro",
            },
            "sentry": mock.ANY,
        }

    def test_create_aws_platform_registry_values_with_role(
        self, aws_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(
            replace(aws_platform_config, aws_role_arn="ecr_role")
        )

        assert result["annotations"] == {"iam.amazonaws.com/role": "ecr_role"}

    def test_create_azure_platform_registry_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(azure_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": azure_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "image": {"repository": "neuro.io/platformregistryapi"},
            "ingress": {
                "enabled": True,
                "hosts": [f"registry.{azure_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-registry-token",
                            "key": "token",
                        }
                    }
                }
            },
            "secrets": [
                {
                    "name": "platform-registry-token",
                    "data": {"token": azure_platform_config.token},
                },
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
        }

    def test_create_on_prem_platform_registry_values(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_registry_values(on_prem_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": on_prem_platform_config.cluster_name,
            "NP_REGISTRY_AUTH_URL": "https://dev.neu.ro",
            "image": {"repository": "neuro.io/platformregistryapi"},
            "ingress": {
                "enabled": True,
                "hosts": [
                    f"registry.{on_prem_platform_config.cluster_name}.org.neu.ro"
                ],
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-registry-token",
                        }
                    }
                }
            },
            "secrets": [
                {
                    "name": "platform-registry-token",
                    "data": {"token": on_prem_platform_config.token},
                },
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
            "NP_MONITORING_PLATFORM_CONFIG_URL": "https://dev.neu.ro",
            "NP_MONITORING_REGISTRY_URL": (
                f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
            ),
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
            "image": {"repository": "neuro.io/platformmonitoringapi"},
            "nodeLabels": {
                "job": "platform.neuromation.io/job",
                "nodePool": "platform.neuromation.io/nodepool",
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-monitoring-token",
                        }
                    }
                }
            },
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "secrets": [
                {
                    "data": {"token": gcp_platform_config.token},
                    "name": "platform-monitoring-token",
                }
            ],
            "containerRuntime": {"name": "docker"},
            "fluentbit": {
                "image": {"repository": "neuro.io/fluent/fluent-bit"},
            },
            "fluentd": {
                "image": {"repository": "neuro.io/bitnami/fluentd"},
                "persistence": {
                    "enabled": True,
                    "storageClassName": "platform-standard-topology-aware",
                },
            },
            "minio": {"image": {"repository": "neuro.io/minio/minio"}},
            "logs": {
                "persistence": {
                    "type": "gcp",
                    "gcp": {
                        "bucket": "job-logs",
                        "project": "project",
                        "location": "us",
                        "serviceAccountKeyBase64": "e30=",
                    },
                }
            },
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
        }

    def test_create_gcp_platform_monitoring_values_with_custom_logs_region(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
            replace(
                gcp_platform_config,
                monitoring=replace(
                    gcp_platform_config.monitoring, logs_region="us-central1"
                ),
            )
        )

        assert result["logs"] == {
            "persistence": {
                "type": "gcp",
                "gcp": {
                    "bucket": "job-logs",
                    "project": "project",
                    "location": "us-central1",
                    "serviceAccountKeyBase64": "e30=",
                },
            }
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
            replace(aws_platform_config, aws_role_arn="s3_role")
        )

        assert result["podAnnotations"] == {"iam.amazonaws.com/role": "s3_role"}
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
                    "accessKey": "username",
                    "secretKey": "password",
                    "region": "minio",
                    "bucket": "job-logs",
                },
            },
        }

    def test_create_on_prem_platform_monitoring_values_with_emc_ecs(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
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

        assert result["logs"] == {
            "persistence": {
                "type": "aws",
                "aws": {
                    "endpoint": "https://emc-ecs.s3",
                    "accessKeyId": "emc_ecs_access_key",
                    "secretAccessKey": "emc_ecs_secret_key",
                    "bucket": "job-logs",
                    "forcePathStyle": True,
                },
            },
        }

    def test_create_on_prem_platform_monitoring_values_with_open_stack(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_monitoring_values(
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

        assert result["logs"] == {
            "persistence": {
                "type": "aws",
                "aws": {
                    "endpoint": "https://os.s3",
                    "accessKeyId": "os_user",
                    "secretAccessKey": "os_password",
                    "region": "os_region",
                    "bucket": "job-logs",
                    "forcePathStyle": True,
                },
            },
        }

    def test_create_gcp_platform_container_runtime_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_container_runtime_values(gcp_platform_config)

        assert result == {
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
        }

    def test_create_platform_secrets_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_secrets_values(gcp_platform_config)

        assert result == {
            "NP_CLUSTER_NAME": gcp_platform_config.cluster_name,
            "NP_SECRETS_K8S_NS": "platform-jobs",
            "NP_SECRETS_PLATFORM_AUTH_URL": "https://dev.neu.ro",
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
            "image": {"repository": "neuro.io/platformsecrets"},
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-secrets-token",
                            "key": "token",
                        }
                    }
                }
            },
            "secrets": [
                {
                    "name": "platform-secrets-token",
                    "data": {"token": gcp_platform_config.token},
                }
            ],
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
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
            "objectStore": {
                "supported": True,
                "configMapName": "thanos-object-storage-config",
            },
            "image": {"repository": "neuro.io/platform-reports"},
            "nvidiaDCGMExporterImage": {"repository": "neuro.io/nvidia/dcgm-exporter"},
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "ingressAuthUrl": "https://platformingressauth",
                "configUrl": "https://dev.neu.ro",
                "apiUrl": "https://dev.neu.ro/api/v1",
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": "platform-reports-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": "platform-reports-token",
                    "data": {"token": gcp_platform_config.token},
                },
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
            "grafanaProxy": {
                "ingress": {
                    "enabled": True,
                    "hosts": [f"metrics.{gcp_platform_config.cluster_name}.org.neu.ro"],
                }
            },
            "prometheus-operator": {
                "global": {
                    "imagePullSecrets": [
                        {"name": "platform-docker-config"},
                        {"name": "platform-docker-hub-config"},
                    ]
                },
                "prometheus": {
                    "prometheusSpec": {
                        "image": {"repository": "neuro.io/prometheus/prometheus"},
                        "retention": "15d",
                        "thanos": {
                            "image": "neuro.io/thanos/thanos:v0.14.0",
                            "version": "v0.14.0",
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
                "prometheusOperator": {
                    "image": {"repository": "neuro.io/coreos/prometheus-operator"},
                    "prometheusConfigReloaderImage": {
                        "repository": ("neuro.io/coreos/prometheus-config-reloader")
                    },
                    "configmapReloadImage": {
                        "repository": "neuro.io/coreos/configmap-reload"
                    },
                    "tlsProxy": {
                        "image": {"repository": "neuro.io/squareup/ghostunnel"}
                    },
                    "admissionWebhooks": {
                        "patch": {
                            "image": {
                                "repository": "neuro.io/jettech/kube-webhook-certgen"
                            }
                        }
                    },
                    "kubeletService": {"namespace": "platform"},
                },
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
                "kube-state-metrics": {
                    "image": {"repository": "neuro.io/coreos/kube-state-metrics"},
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": "platform-docker-config"},
                            {"name": "platform-docker-hub-config"},
                        ]
                    },
                },
                "prometheus-node-exporter": {
                    "image": {"repository": "neuro.io/prometheus/node-exporter"},
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": "platform-docker-config"},
                            {"name": "platform-docker-hub-config"},
                        ]
                    },
                },
            },
            "thanos": {
                "image": {"repository": "neuro.io/thanos/thanos"},
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
                    "name": "platform-reports-gcp-key",
                    "key": "key.json",
                },
            },
            "grafana": {
                "image": {
                    "repository": "neuro.io/grafana/grafana",
                    "pullSecrets": [
                        "platform-docker-config",
                        "platform-docker-hub-config",
                    ],
                },
                "initChownData": {
                    "image": {
                        "repository": "neuro.io/busybox",
                        "pullSecrets": [
                            "platform-docker-config",
                            "platform-docker-hub-config",
                        ],
                    }
                },
                "sidecar": {
                    "image": {
                        "repository": "neuro.io/kiwigrid/k8s-sidecar",
                        "pullSecrets": [
                            "platform-docker-config",
                            "platform-docker-hub-config",
                        ],
                    }
                },
                "adminUser": "admin",
                "adminPassword": "grafana_password",
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
                node_labels=LabelsConfig(
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
            replace(aws_platform_config, aws_role_arn="role_arn")
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
            result["prometheus-operator"]["prometheus"]["prometheusSpec"]["retention"]
            == "15d"
        )
        assert (
            result["prometheus-operator"]["prometheus"]["prometheusSpec"]["thanos"]
            == ""
        )
        assert "cloudProvider" not in result

    def test_create_on_prem_platform_reports_values_with_minio(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
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
                monitoring=MonitoringConfig(
                    logs_bucket_name="job-logs",
                    metrics_storage_type=MetricsStorageType.BUCKETS,
                    metrics_bucket_name="job-metrics",
                ),
            )
        )

        assert result["thanos"]["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "region": "minio",
                "endpoint": "platform-minio:9000",
                "access_key": "minio_access_key",
                "secret_key": "minio_secret_key",
            },
        }

    def test_create_on_prem_platform_reports_values_with_emc_ecs(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
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
                monitoring=MonitoringConfig(
                    logs_bucket_name="job-logs",
                    metrics_storage_type=MetricsStorageType.BUCKETS,
                    metrics_bucket_name="job-metrics",
                ),
            )
        )

        assert result["thanos"]["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "endpoint": "emc-ecs.s3",
                "access_key": "emc_ecs_access_key",
                "secret_key": "emc_ecs_secret_key",
            },
        }

    def test_create_on_prem_platform_reports_values_with_open_stack(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_reports_values(
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
                monitoring=MonitoringConfig(
                    logs_bucket_name="job-logs",
                    metrics_storage_type=MetricsStorageType.BUCKETS,
                    metrics_bucket_name="job-metrics",
                ),
            )
        )

        assert result["thanos"]["objstore"] == {
            "type": "S3",
            "config": {
                "bucket": "job-metrics",
                "region": "os_region",
                "endpoint": "os.s3",
                "access_key": "os_user",
                "secret_key": "os_password",
            },
        }

    def test_create_on_prem_platform_reports_values_with_retention(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        on_prem_platform_config = replace(
            on_prem_platform_config,
            monitoring=replace(
                on_prem_platform_config.monitoring,
                metrics_retention_time="1d",
                metrics_storage_size="10Gi",
            ),
        )

        result = factory.create_platform_reports_values(on_prem_platform_config)

        assert (
            result["prometheus-operator"]["prometheus"]["prometheusSpec"]["retention"]
            == "1d"
        )
        assert (
            result["prometheus-operator"]["prometheus"]["prometheusSpec"][
                "retentionSize"
            ]
            == "10GB"
        )

    def test_create_platform_disk_api_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(gcp_platform_config)

        assert result == {
            "image": {"repository": "neuro.io/platformdiskapi"},
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
                        "secretKeyRef": {"key": "token", "name": "platform-disks-token"}
                    }
                },
            },
            "cors": {
                "origins": [
                    "https://release--neuro-web.netlify.app",
                    "https://app.neu.ro",
                ]
            },
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "secrets": [
                {
                    "name": "platform-disks-token",
                    "data": {"token": gcp_platform_config.token},
                }
            ],
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
        }

    def test_create_platform_disk_api_values_without_storage_class(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(
            replace(on_prem_platform_config, disks_storage_class_name="")
        )

        assert "storageClassName" not in result["disks"]

    def test_create_on_prem_platform_disk_api_values_with_storage_class(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(
            replace(on_prem_platform_config, disks_storage_class_name="openebs-cstor")
        )

        assert result["disks"]["storageClassName"] == "openebs-cstor"

    def test_create_on_prem_platform_disk_api_values_without_cors_origins(
        self, on_prem_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platform_disk_api_values(
            replace(on_prem_platform_config, ingress_cors_origins=())
        )

        assert "cors" not in result

    def test_create_platform_api_poller_values(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platformapi_poller_values(gcp_platform_config)

        assert result == {
            "image": {"repository": "neuro.io/platformapi"},
            "platform": {
                "clusterName": gcp_platform_config.cluster_name,
                "authUrl": "https://dev.neu.ro",
                "configUrl": "https://dev.neu.ro/api/v1",
                "apiUrl": "https://dev.neu.ro/api/v1",
                "registryUrl": (
                    f"https://registry.{gcp_platform_config.cluster_name}.org.neu.ro"
                ),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "key": "token",
                            "name": "platform-poller-token",
                        }
                    }
                },
            },
            "jobs": {
                "namespace": "platform-jobs",
                "ingressClass": "traefik",
                "ingressOAuthAuthorizeUrl": (
                    "https://platformingressauth/oauth/authorize"
                ),
                "imagePullSecret": "platform-docker-hub-config",
            },
            "storages": [{"path": "", "type": "pvc", "claimName": "platform-storage"}],
            "nodeLabels": {
                "job": "platform.neuromation.io/job",
                "gpu": "platform.neuromation.io/accelerator",
                "preemptible": "platform.neuromation.io/preemptible",
                "nodePool": "platform.neuromation.io/nodepool",
            },
            "ingress": {
                "enabled": True,
                "hosts": [f"{gcp_platform_config.cluster_name}.org.neu.ro"],
            },
            "secrets": [
                {
                    "name": "platform-poller-token",
                    "data": {"token": gcp_platform_config.token},
                }
            ],
            "sentry": {
                "dsn": "https://sentry",
                "clusterName": gcp_platform_config.cluster_name,
                "sampleRate": 0.1,
            },
        }

    def test_create_platform_api_poller_values_with_multiple_storages(
        self, gcp_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platformapi_poller_values(
            replace(
                gcp_platform_config,
                storages=[
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        path="/storage1",
                        storage_class_name="class",
                    ),
                    StorageConfig(
                        type=StorageType.KUBERNETES,
                        path="/storage2",
                        storage_class_name="class",
                    ),
                ],
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

    def test_create_azure_platform_api_poller_values(
        self, azure_platform_config: PlatformConfig, factory: HelmValuesFactory
    ) -> None:
        result = factory.create_platformapi_poller_values(azure_platform_config)

        assert (
            result["jobs"]["preemptibleTolerationKey"]
            == "kubernetes.azure.com/scalesetpriority"
        )
