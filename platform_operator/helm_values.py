from base64 import b64decode
from hashlib import sha256
from typing import Any, Dict, Optional

import bcrypt

from .models import (
    BucketsProvider,
    CloudProvider,
    HelmChartNames,
    HelmReleaseNames,
    LabelsConfig,
    MetricsStorageType,
    PlatformConfig,
    RegistryProvider,
    StorageConfig,
    StorageType,
)


class HelmValuesFactory:
    def __init__(
        self,
        helm_release_names: HelmReleaseNames,
        helm_chart_names: HelmChartNames,
        container_runtime: str,
    ) -> None:
        self._release_names = helm_release_names
        self._chart_names = helm_chart_names
        self._container_runtime = container_runtime

    def create_platform_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "kubernetesProvider": platform.kubernetes_provider,
            "traefikEnabled": platform.ingress_controller_install,
            "consulEnabled": platform.consul_install,
            "alpineImage": {"repository": f"{docker_server}/alpine"},
            "pauseImage": {"repository": f"{docker_server}/google_containers/pause"},
            "crictlImage": {"repository": f"{docker_server}/crictl"},
            "serviceToken": platform.token,
            "nodePools": platform.jobs_node_pools,
            "nodeLabels": {
                "nodePool": platform.node_labels.node_pool,
                "job": platform.node_labels.job,
                "gpu": platform.node_labels.accelerator,
            },
            "nvidiaGpuDriver": {
                "image": {"repository": f"{docker_server}/nvidia/k8s-device-plugin"},
            },
            "imagesPrepull": {
                "refreshInterval": "1h",
                "images": [{"image": image} for image in platform.pre_pull_images],
            },
            "ingress": {
                "jobFallbackHost": str(platform.jobs_fallback_host),
                "registryHost": platform.ingress_registry_url.host,
            },
            "jobs": {
                "namespace": {
                    "create": platform.jobs_namespace_create,
                    "name": platform.jobs_namespace,
                },
                "label": platform.node_labels.job,
            },
            "idleJobs": [self._create_idle_job(job) for job in platform.idle_jobs],
            "storages": [self._create_storage_values(s) for s in platform.storages],
            "disks": {
                "storageClass": {
                    "create": CloudProvider.has_value(platform.kubernetes_provider),
                    "name": platform.disks_storage_class_name,
                }
            },
            self._chart_names.traefik: self.create_traefik_values(platform),
            self._chart_names.platform_storage: self.create_platform_storage_values(
                platform
            ),
            self._chart_names.platform_registry: self.create_platform_registry_values(
                platform
            ),
            self._chart_names.platform_monitoring: (
                self.create_platform_monitoring_values(platform)
            ),
            self._chart_names.platform_container_runtime: (
                self.create_platform_container_runtime_values(platform)
            ),
            self._chart_names.platform_secrets: (
                self.create_platform_secrets_values(platform)
            ),
            self._chart_names.platform_reports: (
                self.create_platform_reports_values(platform)
            ),
            self._chart_names.platform_disk_api: (
                self.create_platform_disk_api_values(platform)
            ),
            self._chart_names.platform_api_poller: (
                self.create_platformapi_poller_values(platform)
            ),
            self._chart_names.platform_bucket_api: (
                self.create_platform_buckets_api_values(platform)
            ),
        }
        if platform.docker_config.create_secret:
            result["dockerConfigSecret"] = {
                "create": True,
                "name": platform.docker_config.secret_name,
                "credentials": {
                    "url": str(platform.docker_config.url),
                    "email": platform.docker_config.email,
                    "username": platform.docker_config.username,
                    "password": platform.docker_config.password,
                },
            }
        else:
            result["dockerConfigSecret"] = {"create": False}
        if platform.docker_hub_config and platform.docker_hub_config.create_secret:
            result["dockerHubConfigSecret"] = {
                "create": True,
                "name": platform.docker_hub_config.secret_name,
                "credentials": {
                    "url": str(platform.docker_hub_config.url),
                    "email": platform.docker_hub_config.email,
                    "username": platform.docker_hub_config.username,
                    "password": platform.docker_hub_config.password,
                },
            }
        else:
            result["dockerHubConfigSecret"] = {"create": False}
        if platform.consul_install:
            result[self._chart_names.consul] = self.create_consul_values(platform)
        if platform.registry.docker_registry_install:
            result["dockerRegistryEnabled"] = True
            result[
                self._chart_names.docker_registry
            ] = self.create_docker_registry_values(platform)
        if platform.buckets.minio_install:
            result["minioEnabled"] = True
            result[self._chart_names.minio] = self.create_minio_values(platform)
        return result

    def _create_idle_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        resources = job["resources"]
        result = {
            "name": job["name"],
            "count": job["count"],
            "image": job["image"],
            "imagePullSecrets": [],
            "resources": {
                "cpu": f"{resources['cpu_m']}m",
                "memory": f"{resources['memory_mb']}Mi",
            },
            "env": job.get("env") or {},
            "nodeSelector": job.get("node_selector") or {},
        }
        if "image_pull_secret" in job:
            result["imagePullSecrets"].append({"name": job["image_pull_secret"]})
        if "gpu" in resources:
            result["resources"]["nvidia.com/gpu"] = resources["gpu"]
        return result

    def _create_storage_values(self, storage: StorageConfig) -> Dict[str, Any]:
        if storage.type == StorageType.KUBERNETES:
            return {
                "type": StorageType.KUBERNETES.value,
                "path": storage.path,
                "size": storage.storage_size,
                "storageClassName": storage.storage_class_name,
            }
        if storage.type == StorageType.NFS:
            return {
                "type": StorageType.NFS.value,
                "path": storage.path,
                "size": storage.storage_size,
                "nfs": {
                    "server": storage.nfs_server,
                    "path": storage.nfs_export_path,
                },
            }
        if storage.type == StorageType.SMB:
            return {
                "type": StorageType.SMB.value,
                "path": storage.path,
                "size": storage.storage_size,
                "smb": {
                    "server": storage.smb_server,
                    "shareName": storage.smb_share_name,
                    "username": storage.smb_username,
                    "password": storage.smb_password,
                },
            }
        if storage.type == StorageType.AZURE_fILE:
            return {
                "type": StorageType.AZURE_fILE.value,
                "path": storage.path,
                "size": storage.storage_size,
                "azureFile": {
                    "storageAccountName": storage.azure_storage_account_name,
                    "storageAccountKey": storage.azure_storage_account_key,
                    "shareName": storage.azure_share_name,
                },
            }
        if storage.type == StorageType.GCS:
            return {
                "type": StorageType.GCS.value,
                "path": storage.path,
                "size": storage.storage_size,
                "gcs": {
                    "bucketName": storage.gcs_bucket_name,
                },
            }
        raise ValueError(f"Storage type {storage.type.value!r} is not supported")

    def create_obs_csi_driver_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result = {
            "image": f"{platform.docker_config.url.host}/obs-csi-driver",
            "driverName": "obs.csi.neu.ro",
            "credentialsSecret": {
                "create": True,
                "gcpServiceAccountKeyBase64": platform.gcp_service_account_key_base64,
            },
        }
        if platform.docker_config.create_secret:
            result["imagePullSecret"] = {
                "create": True,
                "credentials": {
                    "url": str(platform.docker_config.url),
                    "email": platform.docker_config.email,
                    "username": platform.docker_config.username,
                    "password": platform.docker_config.password,
                },
            }
        else:
            result["imagePullSecret"] = {
                "create": False,
                "name": platform.docker_config.secret_name,
            }
        return result

    def create_docker_registry_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "image": {"repository": f"{platform.docker_config.url.host}/registry"},
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": platform.registry.docker_registry_storage_class_name,
                "size": platform.registry.docker_registry_storage_size,
            },
            "secrets": {
                "haSharedSecret": sha256(platform.cluster_name.encode()).hexdigest()
            },
            "configData": {"storage": {"delete": {"enabled": True}}},
        }
        if (
            platform.registry.docker_registry_username
            and platform.registry.docker_registry_password
        ):
            username = platform.registry.docker_registry_username
            password_hash = bcrypt.hashpw(
                platform.registry.docker_registry_password.encode(),
                bcrypt.gensalt(rounds=10),
            ).decode()
            result["secrets"]["htpasswd"] = f"{username}:{password_hash}"
        return result

    def create_minio_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.buckets.minio_public_url
        return {
            "image": {
                "repository": f"{platform.docker_config.url.host}/minio/minio",
                "tag": "RELEASE.2021-08-25T00-41-18Z",
            },
            "imagePullSecrets": [
                {"name": name} for name in platform.image_pull_secret_names
            ],
            "DeploymentUpdate": {
                "type": "RollingUpdate",
                "maxUnavailable": 1,
                "maxSurge": 0,
            },
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": platform.buckets.minio_storage_class_name,
                "size": platform.buckets.minio_storage_size,
            },
            "accessKey": platform.buckets.minio_access_key,
            "secretKey": platform.buckets.minio_secret_key,
            "ingress": {
                "enabled": True,
                "annotations": {
                    "kubernetes.io/ingress.class": "traefik",
                    "traefik.frontend.rule.type": "PathPrefix",
                },
                "hosts": [platform.buckets.minio_public_url.host],
            },
            "environment": {"MINIO_REGION_NAME": platform.buckets.minio_region},
        }

    def create_consul_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result = {
            "Image": f"{platform.docker_config.url.host}/consul",
            "StorageClass": platform.standard_storage_class_name,
            "Replicas": 3,
        }
        if not CloudProvider.has_value(platform.kubernetes_provider):
            result["Replicas"] = 1
        return result

    def create_traefik_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        dns_challenge_script_name = "resolve_dns_challenge.sh"
        result: Dict[str, Any] = {
            "replicas": 3,
            "deploymentStrategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
            },
            "image": f"{platform.docker_config.url.host}/traefik",
            "imageTag": "1.7.20-alpine",
            "imagePullSecrets": platform.image_pull_secret_names,
            "logLevel": "debug",
            "serviceType": "LoadBalancer",
            "externalTrafficPolicy": "Cluster",
            "ssl": {"enabled": True, "enforced": True},
            "acme": {
                "enabled": True,
                "onHostRule": False,
                "staging": platform.ingress_acme_environment == "staging",
                "persistence": {"enabled": False},
                "keyType": "RSA4096",
                "challengeType": "dns-01",
                "dnsProvider": {
                    "name": "exec",
                    "exec": {
                        "EXEC_PATH": f"/dns-01/challenge/{dns_challenge_script_name}",
                    },
                },
                "logging": True,
                "email": f"{platform.cluster_name}@neuromation.io",
                "domains": {
                    "enabled": True,
                    "domainsList": [
                        {"main": platform.ingress_url.host},
                        {
                            "sans": [
                                f"*.{platform.ingress_url.host}",
                                f"*.jobs.{platform.ingress_url.host}",
                            ]
                        },
                    ],
                },
            },
            "kvprovider": {
                "consul": {
                    "watch": True,
                    "endpoint": str(platform.consul_url),
                    "prefix": "traefik",
                },
                "storeAcme": True,
                "acmeStorageLocation": "traefik/acme/account",
            },
            "kubernetes": {
                "ingressClass": "traefik",
                "namespaces": [platform.namespace, platform.jobs_namespace],
            },
            "rbac": {"enabled": True},
            "deployment": {
                "labels": {"platform.neuromation.io/app": "ingress"},
                "podLabels": {"platform.neuromation.io/app": "ingress"},
            },
            "extraVolumes": [
                # Mounted secret and configmap volumes are updated automatically
                # by kubelet
                # https://kubernetes.io/docs/tasks/configure-pod-container/configure-pod-configmap/#mounted-configmaps-are-updated-automatically
                # https://kubernetes.io/docs/concepts/configuration/secret/#mounted-secrets-are-updated-automatically
                {
                    "name": "dns-challenge",
                    "configMap": {
                        "name": f"{self._release_names.platform}-dns-challenge",
                        "defaultMode": 0o777,
                    },
                },
                {
                    "name": "dns-challenge-secret",
                    "secret": {
                        "secretName": f"{self._release_names.platform}-dns-challenge"
                    },
                },
            ],
            "extraVolumeMounts": [
                {"name": "dns-challenge", "mountPath": "/dns-01/challenge"},
                {"name": "dns-challenge-secret", "mountPath": "/dns-01/secret"},
            ],
            "env": [
                {"name": "NP_PLATFORM_CONFIG_URL", "value": str(platform.config_url)},
                {"name": "NP_CLUSTER_NAME", "value": platform.cluster_name},
                {
                    "name": "NP_DNS_CHALLENGE_SCRIPT_NAME",
                    "value": dns_challenge_script_name,
                },
            ],
            "resources": {
                "requests": {"cpu": "1200m", "memory": "5Gi"},
                "limits": {"cpu": "1200m", "memory": "5Gi"},
            },
            "timeouts": {"responding": {"idleTimeout": "600s"}},
        }
        if platform.kubernetes_provider == CloudProvider.GCP:
            result["timeouts"] = {
                "responding": {
                    # must be greater than lb timeout
                    # gcp lb default timeout is 600s and cannot be changed
                    "idleTimeout": "660s"  # must be greater than lb timeout
                }
            }
        if platform.kubernetes_provider == CloudProvider.AWS:
            # aws lb default idle timeout is 60s
            # aws network lb default idle timeout is 350s and cannot be changed
            result["service"] = {
                "annotations": {
                    (
                        "service.beta.kubernetes.io/"
                        "aws-load-balancer-connection-idle-timeout"
                    ): "600"
                }
            }
            result["timeouts"] = {
                "responding": {
                    # must be greater than lb timeout
                    "idleTimeout": "660s"  # must be greater than lb timeout
                }
            }
        if platform.kubernetes_provider == CloudProvider.AZURE:
            # azure lb default and minimum idle timeout is 4m, maximum is 30m
            result["service"] = {
                "annotations": {
                    (
                        "service.beta.kubernetes.io/"
                        "azure-load-balancer-tcp-idle-timeout"
                    ): "10"
                }
            }
            result["timeouts"] = {
                "responding": {
                    # must be greater than lb timeout
                    "idleTimeout": "660s"  # must be greater than lb timeout
                }
            }
        if platform.ingress_public_ips:
            result["replicas"] = 1
            result["serviceType"] = "NodePort"
            result["service"] = {
                "nodePorts": {
                    "http": platform.ingress_http_node_port,
                    "https": platform.ingress_https_node_port,
                }
            }
            result["deployment"]["hostPort"] = {
                "httpEnabled": True,
                "httpsEnabled": True,
            }
        return result

    def _create_tracing_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        if not platform.sentry_dsn:
            return {}

        result: Dict[str, Any] = {
            "sentry": {
                "dsn": str(platform.sentry_dsn),
                "clusterName": platform.cluster_name,
            }
        }

        if platform.sentry_sample_rate is not None:
            result["sentry"]["sampleRate"] = platform.sentry_sample_rate

        return result

    def create_platform_storage_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result = {
            "image": {"repository": f"{docker_server}/platformstorageapi"},
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-storage-token",
                            "key": "token",
                        }
                    }
                },
            },
            "storages": [
                {
                    "path": s.path,
                    "type": "pvc",
                    "claimName": platform.get_storage_claim_name(s.path),
                }
                for s in platform.storages
            ],
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-storage-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        if platform.ingress_cors_origins:
            result["cors"] = {"origins": platform.ingress_cors_origins}
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platform_registry_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_REGISTRY_AUTH_URL": str(platform.auth_url),
            "image": {"repository": f"{docker_server}/platformregistryapi"},
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-registry-token",
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_registry_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-registry-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        result.update(**self._create_tracing_values(platform))
        if platform.registry.provider == RegistryProvider.GCP:
            gcp_key_secret_name = f"{self._release_names.platform}-registry-gcp-key"
            result["upstreamRegistry"] = {
                "type": "oauth",
                "url": "https://gcr.io",
                "tokenUrl": "https://gcr.io/v2/token",
                "tokenService": "gcr.io",
                "tokenUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": gcp_key_secret_name,
                            "key": "username",
                        }
                    }
                },
                "tokenPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": gcp_key_secret_name,
                            "key": "password",
                        }
                    }
                },
                "project": platform.registry.gcp_project,
                "maxCatalogEntries": 10000,
            }
            result["secrets"].append(
                {
                    "name": gcp_key_secret_name,
                    "data": {
                        "username": "_json_key",
                        "password": platform.gcp_service_account_key,
                    },
                }
            )
        elif platform.registry.provider == RegistryProvider.AWS:
            result["AWS_DEFAULT_REGION"] = platform.registry.aws_region
            result["upstreamRegistry"] = {
                "type": "aws_ecr",
                "url": (
                    f"https://{platform.registry.aws_account_id}.dkr.ecr"
                    f".{platform.registry.aws_region}.amazonaws.com"
                ),
                "project": "neuro",
                "maxCatalogEntries": 1000,
            }
            if platform.aws_role_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
        elif platform.registry.provider == RegistryProvider.AZURE:
            assert platform.registry.azure_url
            azure_credentials_secret_name = (
                f"{self._release_names.platform}-registry-azure-credentials"
            )
            result["upstreamRegistry"] = {
                "type": "oauth",
                "url": str(platform.registry.azure_url),
                "tokenUrl": str(platform.registry.azure_url / "oauth2/token"),
                "tokenService": platform.registry.azure_url.host,
                "tokenUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": azure_credentials_secret_name,
                            "key": "username",
                        }
                    }
                },
                "tokenPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": azure_credentials_secret_name,
                            "key": "password",
                        }
                    }
                },
                "project": "neuro",
                "maxCatalogEntries": 10000,
            }
            result["secrets"].append(
                {
                    "name": azure_credentials_secret_name,
                    "data": {
                        "username": platform.registry.azure_username,
                        "password": platform.registry.azure_password,
                    },
                }
            )
        elif platform.registry.provider == RegistryProvider.DOCKER:
            docker_registry_credentials_secret_name = (
                f"{self._release_names.platform}-docker-registry"
            )
            result["upstreamRegistry"] = {
                "type": "basic",
                "url": str(platform.registry.docker_registry_url),
                "basicUsername": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": docker_registry_credentials_secret_name,
                            "key": "username",
                        }
                    }
                },
                "basicPassword": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": docker_registry_credentials_secret_name,
                            "key": "password",
                        }
                    }
                },
                "project": "neuro",
                "maxCatalogEntries": 10000,
            }
            result["secrets"].append(
                {
                    "name": docker_registry_credentials_secret_name,
                    "data": {
                        "username": platform.registry.docker_registry_username,
                        "password": platform.registry.docker_registry_password,
                    },
                }
            )
        else:
            assert False, "was unable to construct registry config"
        return result

    def create_platform_monitoring_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "NP_MONITORING_CLUSTER_NAME": platform.cluster_name,
            "NP_MONITORING_K8S_NS": platform.jobs_namespace,
            "NP_MONITORING_PLATFORM_API_URL": str(platform.api_url / "api/v1"),
            "NP_MONITORING_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_MONITORING_PLATFORM_CONFIG_URL": str(platform.config_url),
            "NP_MONITORING_REGISTRY_URL": str(platform.ingress_registry_url),
            "NP_CORS_ORIGINS": ",".join(platform.ingress_cors_origins),
            "image": {"repository": f"{docker_server}/platformmonitoringapi"},
            "nodeLabels": {
                "job": platform.node_labels.job,
                "nodePool": platform.node_labels.node_pool,
            },
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-monitoring-token",
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "containerRuntime": {"name": self._container_runtime},
            "fluentbit": {
                "image": {"repository": f"{docker_server}/fluent/fluent-bit"}
            },
            "fluentd": {
                "image": {"repository": f"{docker_server}/bitnami/fluentd"},
                "persistence": {
                    "enabled": True,
                    "storageClassName": platform.standard_storage_class_name,
                },
            },
            "minio": {"image": {"repository": f"{docker_server}/minio/minio"}},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-monitoring-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        result.update(**self._create_tracing_values(platform))
        if platform.buckets.provider == BucketsProvider.GCP:
            result["logs"] = {
                "persistence": {
                    "type": "gcp",
                    "gcp": {
                        "serviceAccountKeyBase64": (
                            platform.gcp_service_account_key_base64
                        ),
                        "project": platform.buckets.gcp_project,
                        "location": (
                            platform.monitoring.logs_region
                            or platform.buckets.gcp_location
                        ),
                        "bucket": platform.monitoring.logs_bucket_name,
                    },
                }
            }
        elif platform.buckets.provider == BucketsProvider.AWS:
            if platform.aws_role_arn:
                result["podAnnotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
                result["fluentd"]["podAnnotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
            result["logs"] = {
                "persistence": {
                    "type": "aws",
                    "aws": {
                        "region": platform.buckets.aws_region,
                        "bucket": platform.monitoring.logs_bucket_name,
                    },
                }
            }
        elif platform.buckets.provider == BucketsProvider.AZURE:
            result["logs"] = {
                "persistence": {
                    "type": "azure",
                    "azure": {
                        "storageAccountName": (
                            platform.buckets.azure_storage_account_name
                        ),
                        "storageAccountKey": platform.buckets.azure_storage_account_key,
                        "bucket": platform.monitoring.logs_bucket_name,
                    },
                }
            }
        elif platform.buckets.provider == BucketsProvider.MINIO:
            result["logs"] = {
                "persistence": {
                    "type": "minio",
                    "minio": {
                        "url": str(platform.buckets.minio_url),
                        "accessKey": platform.buckets.minio_access_key,
                        "secretKey": platform.buckets.minio_secret_key,
                        "region": platform.buckets.minio_region,
                        "bucket": platform.monitoring.logs_bucket_name,
                    },
                }
            }
            result["NP_MONITORING_K8S_KUBELET_PORT"] = platform.kubelet_port
        else:
            assert False, "was unable to construct monitoring config"
        return result

    def create_platform_container_runtime_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        return {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": platform.node_labels.job,
                                        "operator": "Exists",
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
            **self._create_tracing_values(platform),
        }

    def create_platform_secrets_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_SECRETS_K8S_NS": platform.jobs_namespace,
            "NP_SECRETS_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_CORS_ORIGINS": ",".join(platform.ingress_cors_origins),
            "image": {"repository": f"{docker_server}/platformsecrets"},
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-secrets-token",
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-secrets-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platform_reports_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        object_store_config_map_name = "thanos-object-storage-config"
        relabelings = [
            self._relabel_reports_label(
                platform.node_labels.job,
                LabelsConfig.job,
            ),
            self._relabel_reports_label(
                platform.node_labels.node_pool,
                LabelsConfig.node_pool,
            ),
            self._relabel_reports_label(
                platform.node_labels.accelerator,
                LabelsConfig.accelerator,
            ),
            self._relabel_reports_label(
                platform.node_labels.preemptible,
                LabelsConfig.preemptible,
            ),
        ]
        relabelings = [r for r in relabelings if r]
        if platform.kubernetes_version < "1.17":
            relabelings.append(
                self._relabel_reports_label(
                    "beta.kubernetes.io/instance-type",
                    "node.kubernetes.io/instance-type",
                )
            )
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platform-reports"},
            "nvidiaDCGMExporterImage": {
                "repository": f"{docker_server}/nvidia/dcgm-exporter"
            },
            "nodePoolLabels": {
                "job": platform.node_labels.job,
                "gpu": platform.node_labels.accelerator,
                "nodePool": platform.node_labels.node_pool,
                "preemptible": platform.node_labels.preemptible,
            },
            "objectStore": {
                "supported": True,
                "configMapName": object_store_config_map_name,
            },
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "ingressAuthUrl": str(platform.ingress_auth_url),
                "configUrl": str(platform.config_url),
                "apiUrl": str(platform.api_url / "api/v1"),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-reports-token",
                            "key": "token",
                        }
                    }
                },
            },
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-reports-token",
                    "data": {"token": platform.token},
                }
            ],
            "platformJobs": {"namespace": platform.jobs_namespace},
            "grafanaProxy": {
                "ingress": {
                    "enabled": True,
                    "hosts": [platform.ingress_metrics_url.host],
                }
            },
            "prometheus-operator": {
                "global": {
                    "imagePullSecrets": [
                        {"name": name} for name in platform.image_pull_secret_names
                    ]
                },
                "prometheus": {
                    "prometheusSpec": {
                        "image": {
                            "repository": f"{docker_server}/prometheus/prometheus"
                        },
                        "retention": platform.monitoring.metrics_retention_time,
                        "thanos": {
                            "image": f"{docker_server}/thanos/thanos:v0.14.0",
                            "version": "v0.14.0",
                            "objectStorageConfig": {
                                "name": object_store_config_map_name,
                                "key": "thanos-object-storage.yaml",
                            },
                        },
                        "storageSpec": {
                            "volumeClaimTemplate": {
                                "spec": {
                                    "storageClassName": (
                                        platform.standard_storage_class_name
                                    )
                                },
                            }
                        },
                    }
                },
                "prometheusOperator": {
                    "image": {
                        "repository": f"{docker_server}/coreos/prometheus-operator"
                    },
                    "prometheusConfigReloaderImage": {
                        "repository": (
                            f"{docker_server}/coreos/prometheus-config-reloader"
                        )
                    },
                    "configmapReloadImage": {
                        "repository": f"{docker_server}/coreos/configmap-reload"
                    },
                    "tlsProxy": {
                        "image": {"repository": f"{docker_server}/squareup/ghostunnel"}
                    },
                    "admissionWebhooks": {
                        "patch": {
                            "image": {
                                "repository": (
                                    f"{docker_server}/jettech/kube-webhook-certgen"
                                )
                            }
                        }
                    },
                    "kubeletService": {"namespace": platform.namespace},
                },
                "kubelet": {"namespace": platform.namespace},
                "kubeStateMetrics": {
                    "serviceMonitor": {"metricRelabelings": relabelings}
                },
                "kube-state-metrics": {
                    "image": {
                        "repository": f"{docker_server}/coreos/kube-state-metrics"
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": name} for name in platform.image_pull_secret_names
                        ]
                    },
                },
                "prometheus-node-exporter": {
                    "image": {
                        "repository": f"{docker_server}/prometheus/node-exporter"
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": name} for name in platform.image_pull_secret_names
                        ]
                    },
                },
            },
            "thanos": {
                "image": {"repository": f"{docker_server}/thanos/thanos"},
                "store": {
                    "persistentVolumeClaim": {
                        "spec": {
                            "storageClassName": platform.standard_storage_class_name,
                        },
                    },
                },
                "compact": {
                    "persistentVolumeClaim": {
                        "spec": {
                            "storageClassName": platform.standard_storage_class_name,
                        },
                    },
                },
            },
            "grafana": {
                "image": {
                    "repository": f"{docker_server}/grafana/grafana",
                    "pullSecrets": platform.image_pull_secret_names,
                },
                "initChownData": {
                    "image": {
                        "repository": f"{docker_server}/busybox",
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "sidecar": {
                    "image": {
                        "repository": f"{docker_server}/kiwigrid/k8s-sidecar",
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "adminUser": platform.grafana_username,
                "adminPassword": platform.grafana_password,
            },
        }
        result.update(**self._create_tracing_values(platform))
        prometheus_spec = result["prometheus-operator"]["prometheus"]["prometheusSpec"]
        if platform.monitoring.metrics_storage_type == MetricsStorageType.KUBERNETES:
            result["objectStore"] = {"supported": False}
            result["prometheusProxy"] = {
                "prometheus": {"host": "prometheus-prometheus", "port": 9090}
            }
            prometheus_spec["retentionSize"] = (
                platform.monitoring.metrics_storage_size.replace("i", "")
                + "B"  # Gi -> GB
            )
            prometheus_spec["storageSpec"]["volumeClaimTemplate"]["spec"] = {
                "storageClassName": platform.monitoring.metrics_storage_class_name,
                "resources": {
                    "requests": {"storage": platform.monitoring.metrics_storage_size}
                },
            }
            # Because of the bug in helm the only way to delete thanos values
            # is to set it to empty string
            prometheus_spec["thanos"] = ""
            del result["thanos"]
        elif platform.buckets.provider == BucketsProvider.GCP:
            result["thanos"]["objstore"] = {
                "type": "GCS",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "service_account": b64decode(
                        platform.gcp_service_account_key_base64
                    ).decode(),
                },
            }
            result["secrets"].append(
                {
                    "name": f"{self._release_names.platform}-reports-gcp-key",
                    "data": {"key.json": platform.gcp_service_account_key},
                }
            )
        elif platform.buckets.provider == BucketsProvider.AWS:
            if platform.aws_role_arn:
                result["metricsServer"] = {
                    "podMetadata": {
                        "annotations": {"iam.amazonaws.com/role": platform.aws_role_arn}
                    }
                }
                prometheus_spec["podMetadata"] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws_role_arn}
                }
                result["thanos"]["store"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
                result["thanos"]["bucket"] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws_role_arn}
                }
                result["thanos"]["compact"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": f"s3.{platform.buckets.aws_region}.amazonaws.com",
                },
            }
        elif platform.buckets.provider == BucketsProvider.AZURE:
            result["thanos"]["objstore"] = {
                "type": "AZURE",
                "config": {
                    "container": platform.monitoring.metrics_bucket_name,
                    "storage_account": platform.buckets.azure_storage_account_name,
                    "storage_account_key": platform.buckets.azure_storage_account_key,
                },
            }
        elif platform.buckets.provider == BucketsProvider.MINIO:
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": str(platform.buckets.minio_url),
                    "region": platform.buckets.minio_region,
                    "access_key": platform.buckets.minio_access_key,
                    "secret_key": platform.buckets.minio_secret_key,
                },
            }
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": str(platform.buckets.emc_ecs_s3_endpoint),
                    "access_key": platform.buckets.emc_ecs_access_key_id,
                    "secret_key": platform.buckets.emc_ecs_secret_access_key,
                },
            }
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": str(platform.buckets.open_stack_s3_endpoint),
                    "region": platform.buckets.open_stack_region_name,
                    "access_key": platform.buckets.open_stack_username,
                    "secret_key": platform.buckets.open_stack_password,
                },
            }
        else:
            assert False, "was unable to construct thanos object store config"
        if platform.kubernetes_provider == CloudProvider.GCP:
            result["cloudProvider"] = {
                "type": "gcp",
                "region": platform.monitoring.metrics_region,
                "serviceAccountSecret": {
                    "name": f"{self._release_names.platform}-reports-gcp-key",
                    "key": "key.json",
                },
            }
        if platform.kubernetes_provider == CloudProvider.AWS:
            result["cloudProvider"] = {
                "type": "aws",
                "region": platform.monitoring.metrics_region,
            }
        if platform.kubernetes_provider == CloudProvider.AZURE:
            result["cloudProvider"] = {
                "type": "azure",
                "region": platform.monitoring.metrics_region,
            }
        return result

    def _relabel_reports_label(
        self, source_label: str, target_label: str
    ) -> Optional[Dict[str, Any]]:
        if source_label == target_label:
            return None
        return {
            "sourceLabels": [self._convert_label_to_reports_value(source_label)],
            "targetLabel": self._convert_label_to_reports_value(target_label),
        }

    def _convert_label_to_reports_value(self, value: str) -> str:
        return "label_" + value.replace(".", "_").replace("/", "_").replace("-", "_")

    def create_platform_disk_api_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platformdiskapi"},
            "disks": {
                "namespace": platform.jobs_namespace,
                "limitPerUser": str(
                    platform.disks_storage_limit_per_user_gb * 1024 ** 3
                ),
            },
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-disks-token",
                            "key": "token",
                        }
                    }
                },
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-disks-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        if platform.ingress_cors_origins:
            result["cors"] = {"origins": platform.ingress_cors_origins}
        if platform.disks_storage_class_name:
            result["disks"]["storageClassName"] = platform.disks_storage_class_name
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platformapi_poller_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platformapi"},
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "configUrl": str(platform.config_url / "api/v1"),
                "apiUrl": str(platform.api_url / "api/v1"),
                "registryUrl": str(platform.ingress_registry_url),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-poller-token",
                            "key": "token",
                        }
                    }
                },
            },
            "jobs": {
                "namespace": platform.jobs_namespace,
                "ingressClass": "traefik",
                "ingressOAuthAuthorizeUrl": str(
                    platform.ingress_auth_url / "oauth/authorize"
                ),
            },
            "nodeLabels": {
                "job": platform.node_labels.job,
                "gpu": platform.node_labels.accelerator,
                "preemptible": platform.node_labels.preemptible,
                "nodePool": platform.node_labels.node_pool,
            },
            "storages": [
                {
                    "path": s.path,
                    "type": "pvc",
                    "claimName": platform.get_storage_claim_name(s.path),
                }
                for s in platform.storages
            ],
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-poller-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        result.update(**self._create_tracing_values(platform))
        if platform.kubernetes_provider == CloudProvider.AZURE:
            result["jobs"][
                "preemptibleTolerationKey"
            ] = "kubernetes.azure.com/scalesetpriority"
        if platform.docker_hub_config:
            result["jobs"]["imagePullSecret"] = platform.docker_hub_config.secret_name
        return result

    def create_platform_buckets_api_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_config.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platformbucketsapi"},
            "bucketNamespace": platform.jobs_namespace,
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": (
                                f"{self._release_names.platform}-buckets-api-token"
                            ),
                            "key": "token",
                        }
                    }
                },
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-buckets-api-token",
                    "data": {"token": platform.token},
                }
            ],
            "disableCreation": platform.buckets.disable_creation,
        }
        if platform.ingress_cors_origins:
            result["cors"] = {"origins": platform.ingress_cors_origins}
        result.update(**self._create_tracing_values(platform))
        if platform.buckets.provider == BucketsProvider.AWS:
            result["bucketProvider"] = {
                "type": "aws",
                "aws": {
                    "regionName": platform.buckets.aws_region,
                    "s3RoleArn": platform.aws_s3_role_arn,
                },
            }
            if platform.aws_role_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws_role_arn
                }
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            secret_name = f"{self._release_names.platform}-buckets-emc-ecs-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {
                        "key": platform.buckets.emc_ecs_access_key_id,
                        "secret": platform.buckets.emc_ecs_secret_access_key,
                    },
                }
            )
            result["bucketProvider"] = {
                "type": "emc_ecs",
                "emc_ecs": {
                    "s3RoleUrn": platform.buckets.emc_ecs_s3_assumable_role,
                    "accessKeyId": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "key",
                            }
                        }
                    },
                    "secretAccessKey": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "secret",
                            }
                        }
                    },
                    "s3EndpointUrl": str(platform.buckets.emc_ecs_s3_endpoint),
                    "managementEndpointUrl": str(
                        platform.buckets.emc_ecs_management_endpoint
                    ),
                },
            }
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            secret_name = f"{self._release_names.platform}-buckets-open-stack-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {
                        "accountId": platform.buckets.open_stack_username,
                        "password": platform.buckets.open_stack_password,
                    },
                }
            )
            result["bucketProvider"] = {
                "type": "open_stack",
                "open_stack": {
                    "regionName": platform.buckets.open_stack_region_name,
                    "accountId": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "accountId",
                            }
                        }
                    },
                    "password": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "password",
                            }
                        }
                    },
                    "s3EndpointUrl": str(platform.buckets.open_stack_s3_endpoint),
                    "endpointUrl": str(platform.buckets.open_stack_endpoint),
                },
            }
        elif platform.buckets.provider == BucketsProvider.MINIO:
            result["bucketProvider"] = {
                "type": "minio",
                "minio": {
                    "url": str(platform.buckets.minio_url),
                    "publicUrl": str(platform.buckets.minio_public_url),
                    "accessKeyId": platform.buckets.minio_access_key,
                    "secretAccessKey": platform.buckets.minio_secret_key,
                    "regionName": platform.buckets.minio_region,
                },
            }
        elif platform.buckets.provider == BucketsProvider.AZURE:
            secret_name = (
                f"{self._release_names.platform}-buckets-azure-storage-account-key"
            )
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {"key": platform.buckets.azure_storage_account_key},
                }
            )
            result["bucketProvider"] = {
                "type": "azure",
                "azure": {
                    "url": (
                        f"https://{platform.buckets.azure_storage_account_name}"
                        f".blob.core.windows.net"
                    ),
                    "credential": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "key",
                            }
                        }
                    },
                },
            }
        elif platform.buckets.provider == BucketsProvider.GCP:
            secret_name = f"{self._release_names.platform}-buckets-gcp-sa-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {"SAKeyB64": platform.gcp_service_account_key_base64},
                }
            )
            result["bucketProvider"] = {
                "type": "gcp",
                "gcp": {
                    "SAKeyJsonB64": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "SAKeyB64",
                            }
                        }
                    }
                },
            }
        else:
            assert False, "was unable to construct bucket provider"
        return result
