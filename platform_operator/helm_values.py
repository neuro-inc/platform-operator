from __future__ import annotations

from base64 import b64decode
from hashlib import sha256
from typing import Any

import bcrypt
from neuro_config_client import ACMEEnvironment, CloudProviderType, IdleJobConfig
from yarl import URL

from .models import (
    BucketsProvider,
    HelmChartNames,
    IngressServiceType,
    LabelsConfig,
    MetricsStorageType,
    PlatformConfig,
    RegistryProvider,
    StorageConfig,
    StorageType,
)


class HelmValuesFactory:
    def __init__(
        self, helm_chart_names: HelmChartNames, container_runtime: str
    ) -> None:
        self._chart_names = helm_chart_names
        self._container_runtime = container_runtime

    def create_platform_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kubernetesProvider": platform.kubernetes_provider,
            "traefikEnabled": platform.ingress_controller_install,
            "acmeEnabled": platform.ingress_acme_enabled,
            "dockerRegistryEnabled": platform.registry.docker_registry_install,
            "minioEnabled": platform.buckets.minio_install,
            "platformReportsEnabled": platform.monitoring.metrics_enabled,
            "alpineImage": {"repository": platform.get_image("alpine")},
            "pauseImage": {"repository": platform.get_image("pause")},
            "crictlImage": {"repository": platform.get_image("crictl")},
            "kubectlImage": {"repository": platform.get_image("kubectl")},
            "clusterName": platform.cluster_name,
            "serviceToken": platform.token,
            "nodePools": [
                {
                    "name": rpt.name,
                    "idleSize": rpt.idle_size,
                    "cpu": rpt.available_cpu,
                    "gpu": rpt.gpu or 0,
                }
                for rpt in platform.jobs_resource_pool_types
            ],
            "nodeLabels": {
                "nodePool": platform.node_labels.node_pool,
                "job": platform.node_labels.job,
                "gpu": platform.node_labels.accelerator,
            },
            "nvidiaGpuDriver": {
                "image": {"repository": platform.get_image("k8s-device-plugin")},
            },
            "nvidiaDCGMExporter": {
                "image": {"repository": platform.get_image("dcgm-exporter")},
                "serviceMonitor": {"enabled": platform.monitoring.metrics_enabled},
            },
            "imagesPrepull": {
                "refreshInterval": "1h",
                "images": [{"image": image} for image in platform.pre_pull_images],
            },
            "serviceAccount": {"annotations": platform.service_account_annotations},
            "ingress": {
                "jobFallbackHost": str(platform.jobs_fallback_host),
                "registryHost": platform.ingress_registry_url.host,
                "ingressAuthHost": platform.ingress_auth_url.host,
            },
            "ssl": {
                "cert": platform.ingress_ssl_cert_data,
                "key": platform.ingress_ssl_cert_key_data,
            },
            "jobs": {
                "namespace": {
                    "create": True,
                    "name": platform.jobs_namespace,
                },
                "label": platform.node_labels.job,
            },
            "idleJobs": [self._create_idle_job(job) for job in platform.idle_jobs],
            "storages": [self._create_storage_values(s) for s in platform.storages],
            self._chart_names.traefik: self.create_traefik_values(platform),
            self._chart_names.platform_storage: self.create_platform_storage_values(
                platform
            ),
            self._chart_names.platform_registry: self.create_platform_registry_values(
                platform
            ),
            self._chart_names.platform_monitoring: self.create_platform_monitoring_values(  # noqa
                platform
            ),
            self._chart_names.platform_container_runtime: self.create_platform_container_runtime_values(  # noqa
                platform
            ),
            self._chart_names.platform_secrets: self.create_platform_secrets_values(
                platform
            ),
            self._chart_names.platform_disks: self.create_platform_disks_values(
                platform
            ),
            self._chart_names.platform_api_poller: self.create_platform_api_poller_values(  # noqa
                platform
            ),
            self._chart_names.platform_buckets: self.create_platform_buckets_values(
                platform
            ),
        }
        if platform.ingress_acme_enabled:
            result["acme"] = self.create_acme_values(platform)
        if platform.ingress_cors_origins:
            result["ingress"]["cors"] = {"originList": platform.ingress_cors_origins}
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
        if platform.registry.docker_registry_install:
            result[
                self._chart_names.docker_registry
            ] = self.create_docker_registry_values(platform)
        if platform.buckets.minio_install:
            assert platform.buckets.minio_public_url
            result["ingress"]["minioHost"] = platform.buckets.minio_public_url.host
            result[self._chart_names.minio] = self.create_minio_values(platform)
        if platform.monitoring.metrics_enabled:
            result[
                self._chart_names.platform_reports
            ] = self.create_platform_reports_values(platform)
        return result

    def create_acme_values(self, platform: PlatformConfig) -> dict[str, Any]:
        return {
            "nameOverride": "acme",
            "fullnameOverride": "acme",
            "bashImage": {"repository": platform.get_image("bash")},
            "acme": {
                "email": f"{platform.cluster_name}@neu.ro",
                "dns": "neuro",
                "server": (
                    "letsencrypt"
                    if platform.ingress_acme_environment == ACMEEnvironment.PRODUCTION
                    else "letsencrypt_test"
                ),
                "domains": [
                    platform.ingress_url.host,
                    f"*.{platform.ingress_url.host}",
                    f"*.jobs.{platform.ingress_url.host}",
                ],
                "sslCertSecretName": f"{platform.release_name}-ssl-cert",
                "rolloutDeploymentName": "traefik",
            },
            "podLabels": {"service": "acme"},
            "env": [
                {"name": "NEURO_URL", "value": str(platform.auth_url)},
                {"name": "NEURO_CLUSTER", "value": platform.cluster_name},
                {
                    "name": "NEURO_TOKEN",
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{platform.release_name}-token",
                            "key": "token",
                        }
                    },
                },
            ],
            "persistence": {"storageClassName": platform.standard_storage_class_name},
            "priorityClassName": platform.services_priority_class_name,
        }

    def _create_idle_job(self, job: IdleJobConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": job.name,
            "count": job.count,
            "image": job.image,
            "resources": {
                "cpu": f"{job.resources.cpu_m}m",
                "memory": f"{job.resources.memory}",
            },
        }
        if job.command:
            result["command"] = job.command
        if job.args:
            result["args"] = job.args
        if job.image_pull_secret:
            result["imagePullSecrets"] = [{"name": job.image_pull_secret}]
        if job.resources.gpu:
            result["resources"]["nvidia.com/gpu"] = job.resources.gpu
        if job.env:
            result["env"] = job.env
        if job.node_selector:
            result["nodeSelector"] = job.node_selector
        return result

    def _create_storage_values(self, storage: StorageConfig) -> dict[str, Any]:
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

    def create_docker_registry_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "image": {"repository": platform.get_image("registry")},
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
            "podLabels": {"service": "docker-registry"},
            "priorityClassName": platform.services_priority_class_name,
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

    def create_minio_values(self, platform: PlatformConfig) -> dict[str, Any]:
        assert platform.buckets.minio_public_url
        return {
            "image": {
                "repository": platform.get_image("minio"),
                "tag": "RELEASE.2022-03-08T22-28-51Z",
            },
            "imagePullSecrets": [
                {"name": name} for name in platform.image_pull_secret_names
            ],
            "DeploymentUpdate": {
                "type": "RollingUpdate",
                "maxUnavailable": 1,
                "maxSurge": 0,
            },
            "resources": {
                "requests": {
                    "cpu": "100m",
                    "memory": "1Gi",
                },
            },
            "podLabels": {"service": "minio"},
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": platform.buckets.minio_storage_class_name,
                "size": platform.buckets.minio_storage_size,
            },
            "accessKey": platform.buckets.minio_access_key,
            "secretKey": platform.buckets.minio_secret_key,
            "ingress": {"enabled": False},
            "priorityClassName": platform.services_priority_class_name,
        }

    def create_traefik_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": "traefik",
            "fullnameOverride": "traefik",
            "instanceLabelOverride": "traefik",
            "image": {"name": platform.get_image("traefik")},
            "deployment": {
                "replicas": platform.ingress_controller_replicas,
                "labels": {"service": "traefik"},
                "podLabels": {"service": "traefik"},
                "imagePullSecrets": [
                    {"name": name} for name in platform.image_pull_secret_names
                ],
            },
            "resources": {
                "requests": {"cpu": "250m", "memory": "256Mi"},
                "limits": {"cpu": "1000m", "memory": "1Gi"},
            },
            "service": {
                "type": platform.ingress_service_type.value,
                "annotations": {},
            },
            "ports": {
                "web": {"redirectTo": "websecure"},
                "websecure": {"tls": {"enabled": True}},
            },
            "additionalArguments": [
                "--entryPoints.websecure.proxyProtocol.insecure=true",
                "--entryPoints.websecure.forwardedHeaders.insecure=true",
                "--entryPoints.websecure.http.middlewares="
                f"{platform.namespace}-{platform.release_name}-cors@kubernetescrd",
                "--providers.file.filename=/etc/traefik/dynamic/config.yaml",
            ],
            "volumes": [
                {
                    "name": f"{platform.release_name}-traefik-dynamic-config",
                    "mountPath": "/etc/traefik/dynamic",
                    "type": "configMap",
                },
                {
                    "name": f"{platform.release_name}-ssl-cert",
                    "mountPath": "/etc/certs",
                    "type": "secret",
                },
            ],
            "providers": {
                "kubernetesCRD": {
                    "enabled": True,
                    "allowCrossNamespace": True,
                    "allowExternalNameServices": True,
                    "namespaces": platform.ingress_namespaces,
                },
                "kubernetesIngress": {
                    "enabled": True,
                    "allowExternalNameServices": True,
                    "namespaces": platform.ingress_namespaces,
                },
            },
            "ingressRoute": {"dashboard": {"enabled": False}},
            "logs": {"general": {"level": "ERROR"}},
            "priorityClassName": platform.services_priority_class_name,
        }
        if platform.kubernetes_version >= "1.19":
            result["ingressClass"] = {"enabled": True}
        if platform.kubernetes_provider == CloudProviderType.AWS:
            result["service"]["annotations"] = {
                "service.beta.kubernetes.io/aws-load-balancer-type": "external",
                "service.beta.kubernetes.io/aws-load-balancer-nlb-target-type": (
                    "instance"
                ),
                "service.beta.kubernetes.io/aws-load-balancer-scheme": (
                    "internet-facing"
                ),
            }
        if platform.ingress_load_balancer_source_ranges:
            result["service"][
                "loadBalancerSourceRanges"
            ] = platform.ingress_load_balancer_source_ranges
        if platform.ingress_service_type == IngressServiceType.NODE_PORT:
            result["rollingUpdate"] = {"maxUnavailable": 1, "maxSurge": 0}
            ports = result["ports"]
            if platform.ingress_node_port_http and platform.ingress_node_port_https:
                ports["web"]["nodePort"] = platform.ingress_node_port_http
                ports["websecure"]["nodePort"] = platform.ingress_node_port_https
            if platform.ingress_host_port_http and platform.ingress_host_port_https:
                ports["web"]["hostPort"] = platform.ingress_host_port_http
                ports["websecure"]["hostPort"] = platform.ingress_host_port_https
        result["service"]["annotations"].update(platform.ingress_service_annotations)
        return result

    def _create_platform_url_value(
        self, name: str, url: URL, path: str = ""
    ) -> dict[str, str]:
        if url == URL("-"):
            return {name: "-"}
        if path:
            return {name: str(URL(url) / path)}
        return {name: str(url)}

    def _create_platform_token_value(self, platform: PlatformConfig) -> dict[str, Any]:
        if platform.token:
            return {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{platform.release_name}-token",
                            "key": "token",
                        }
                    }
                }
            }
        return {
            "token": {"value": ""},
        }

    def _create_tracing_values(self, platform: PlatformConfig) -> dict[str, Any]:
        if not platform.sentry_dsn:
            return {}
        result = {
            "sentry": {
                "dsn": str(platform.sentry_dsn),
                "clusterName": platform.cluster_name,
                "sampleRate": platform.sentry_sample_rate,
            }
        }
        return result

    def create_platform_storage_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result = {
            "nameOverride": f"{platform.release_name}-storage",
            "fullnameOverride": f"{platform.release_name}-storage",
            "image": {"repository": platform.get_image("platformstorageapi")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
            },
            "storages": [
                {
                    "path": s.path,
                    "type": "pvc",
                    "claimName": platform.get_storage_claim_name(s.path),
                }
                for s in platform.storages
            ],
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
                "hosts": [platform.ingress_url.host],
            },
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platform_registry_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-registry",
            "fullnameOverride": f"{platform.release_name}-registry",
            "image": {"repository": platform.get_image("platformregistryapi")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
            },
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
                "hosts": [platform.ingress_registry_url.host],
            },
            "secrets": [],
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        if platform.registry.provider == RegistryProvider.GCP:
            gcp_key_secret_name = f"{platform.release_name}-registry-gcp-key"
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
            result["upstreamRegistry"] = {
                "type": "aws_ecr",
                "url": (
                    f"https://{platform.registry.aws_account_id}.dkr.ecr"
                    f".{platform.registry.aws_region}.amazonaws.com"
                ),
                "region": platform.registry.aws_region,
                "project": "neuro",
                "maxCatalogEntries": 1000,
            }
        elif platform.registry.provider == RegistryProvider.AZURE:
            assert platform.registry.azure_url
            azure_credentials_secret_name = (
                f"{platform.release_name}-registry-azure-credentials"
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
                f"{platform.release_name}-docker-registry"
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
            raise AssertionError("was unable to construct registry config")
        return result

    def create_platform_monitoring_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-monitoring",
            "fullnameOverride": f"{platform.release_name}-monitoring",
            "image": {"repository": platform.get_image("platformmonitoringapi")},
            "jobsNamespace": platform.jobs_namespace,
            "kubeletPort": platform.kubelet_port,
            "nvidiaDCGMPort": platform.nvidia_dcgm_port,
            "nodeLabels": {
                "job": platform.node_labels.job,
                "nodePool": platform.node_labels.node_pool,
            },
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_url_value("configUrl", platform.config_url),
                **self._create_platform_url_value("apiUrl", platform.api_url, "api/v1"),
                **self._create_platform_url_value(
                    "registryUrl", platform.ingress_registry_url
                ),
                **self._create_platform_token_value(platform),
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
                "hosts": [platform.ingress_url.host],
            },
            "containerRuntime": {"name": self._container_runtime},
            "fluentbit": {"image": {"repository": platform.get_image("fluent-bit")}},
            "minioGateway": {"image": {"repository": platform.get_image("minio")}},
            "priorityClassName": platform.services_priority_class_name,
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
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            result["logs"] = {
                "persistence": {
                    "type": "aws",
                    "aws": {
                        "endpoint": str(platform.buckets.emc_ecs_s3_endpoint),
                        "accessKeyId": platform.buckets.emc_ecs_access_key_id,
                        "secretAccessKey": platform.buckets.emc_ecs_secret_access_key,
                        "bucket": platform.monitoring.logs_bucket_name,
                        "forcePathStyle": True,
                    },
                }
            }
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            result["logs"] = {
                "persistence": {
                    "type": "aws",
                    "aws": {
                        "endpoint": str(platform.buckets.open_stack_s3_endpoint),
                        "accessKeyId": platform.buckets.open_stack_username,
                        "secretAccessKey": platform.buckets.open_stack_password,
                        "region": platform.buckets.open_stack_region_name,
                        "bucket": platform.monitoring.logs_bucket_name,
                        "forcePathStyle": True,
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
        else:
            raise AssertionError("was unable to construct monitoring config")
        return result

    def create_platform_container_runtime_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        return {
            "nameOverride": f"{platform.release_name}-container-runtime",
            "fullnameOverride": f"{platform.release_name}-container-runtime",
            "image": {"repository": platform.get_image("platformcontainerruntime")},
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
            "priorityClassName": platform.services_priority_class_name,
            **self._create_tracing_values(platform),
        }

    def create_platform_secrets_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-secrets",
            "fullnameOverride": f"{platform.release_name}-secrets",
            "image": {"repository": platform.get_image("platformsecrets")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
            },
            "secretsNamespace": platform.jobs_namespace,
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
                "hosts": [platform.ingress_url.host],
            },
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platform_reports_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
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
        result: dict[str, Any] = {
            "image": {"repository": platform.get_image("platform-reports")},
            "nodePoolLabels": {
                "job": platform.node_labels.job,
                "gpu": platform.node_labels.accelerator,
                "nodePool": platform.node_labels.node_pool,
                "preemptible": platform.node_labels.preemptible,
            },
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_url_value(
                    "ingressAuthUrl", platform.ingress_auth_url
                ),
                **self._create_platform_url_value("configUrl", platform.config_url),
                **self._create_platform_url_value("apiUrl", platform.api_url, "api/v1"),
                **self._create_platform_token_value(platform),
            },
            "secrets": [],
            "platformJobs": {"namespace": platform.jobs_namespace},
            "grafanaProxy": {
                "ingress": {
                    "enabled": True,
                    "ingressClassName": "traefik",
                    "hosts": [platform.ingress_metrics_url.host],
                    "annotations": {
                        "traefik.ingress.kubernetes.io/router.middlewares": (
                            f"{platform.namespace}-{platform.release_name}-ingress-auth"
                            "@kubernetescrd"
                        ),
                    },
                }
            },
            "prometheusRemoteStorageEnabled": True,
            "kube-prometheus-stack": {
                "global": {
                    "imageRegistry": platform.image_registry,
                    "imagePullSecrets": [
                        {"name": name} for name in platform.image_pull_secret_names
                    ],
                },
                "prometheus": {
                    "prometheusSpec": {
                        "image": {
                            "registry": platform.image_registry,
                            "repository": platform.get_image_repo("prometheus"),
                        },
                        "retention": platform.monitoring.metrics_retention_time,
                        "storageSpec": {
                            "volumeClaimTemplate": {
                                "spec": {
                                    "storageClassName": (
                                        platform.standard_storage_class_name
                                    )
                                },
                            }
                        },
                        "externalLabels": {
                            "cluster": platform.cluster_name,
                        },
                        "priorityClassName": platform.services_priority_class_name,
                    }
                },
                "prometheusOperator": {
                    "image": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("prometheus-operator"),
                    },
                    "prometheusConfigReloader": {
                        "image": {
                            "registry": platform.image_registry,
                            "repository": platform.get_image_repo(
                                "prometheus-config-reloader"
                            ),
                        }
                    },
                    "thanosImage": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("thanos"),
                    },
                    "admissionWebhooks": {
                        "patch": {
                            "image": {
                                "registry": platform.image_registry,
                                "repository": platform.get_image_repo(
                                    "kube-webhook-certgen"
                                ),
                            },
                            "priorityClassName": platform.services_priority_class_name,
                        }
                    },
                    "kubeletService": {"namespace": platform.namespace},
                    "priorityClassName": platform.services_priority_class_name,
                },
                "kubelet": {"namespace": platform.namespace},
                "kubeStateMetrics": {
                    "serviceMonitor": {"metricRelabelings": relabelings}
                },
                "kube-state-metrics": {
                    "image": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("kube-state-metrics"),
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": name} for name in platform.image_pull_secret_names
                        ]
                    },
                    "priorityClassName": platform.services_priority_class_name,
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
                                        "metricNamePrefix": "platform",
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
                "prometheus-node-exporter": {
                    "image": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("node-exporter"),
                    },
                    "serviceAccount": {
                        "imagePullSecrets": [
                            {"name": name} for name in platform.image_pull_secret_names
                        ]
                    },
                },
            },
            "thanos": {
                "image": {"repository": platform.get_image("thanos")},
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
                "priorityClassName": platform.services_priority_class_name,
            },
            "grafana": {
                "image": {
                    "registry": platform.image_registry,
                    "repository": platform.get_image_repo("grafana"),
                    "pullSecrets": platform.image_pull_secret_names,
                },
                "initChownData": {
                    "image": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("busybox"),
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "sidecar": {
                    "image": {
                        "registry": platform.image_registry,
                        "repository": platform.get_image_repo("k8s-sidecar"),
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "adminUser": platform.grafana_username,
                "adminPassword": platform.grafana_password,
                "priorityClassName": platform.services_priority_class_name,
            },
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        prometheus_spec = result["kube-prometheus-stack"]["prometheus"][
            "prometheusSpec"
        ]
        if platform.monitoring.metrics_storage_type == MetricsStorageType.KUBERNETES:
            result["prometheusRemoteStorageEnabled"] = False
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
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
            }
            result["secrets"].append(
                {
                    "name": f"{platform.release_name}-reports-gcp-key",
                    "data": {"key.json": platform.gcp_service_account_key},
                }
            )
        elif platform.buckets.provider == BucketsProvider.AWS:
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": f"s3.{platform.buckets.aws_region}.amazonaws.com",
                },
            }
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
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
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
            }
        elif platform.buckets.provider == BucketsProvider.MINIO:
            assert platform.buckets.minio_url
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": self._get_url_authority(platform.buckets.minio_url),
                    "region": platform.buckets.minio_region,
                    "access_key": platform.buckets.minio_access_key,
                    "secret_key": platform.buckets.minio_secret_key,
                },
            }
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
            }
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            assert platform.buckets.emc_ecs_s3_endpoint
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": self._get_url_authority(
                        platform.buckets.emc_ecs_s3_endpoint
                    ),
                    "access_key": platform.buckets.emc_ecs_access_key_id,
                    "secret_key": platform.buckets.emc_ecs_secret_access_key,
                },
            }
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
            }
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            assert platform.buckets.open_stack_s3_endpoint
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring.metrics_bucket_name,
                    "endpoint": self._get_url_authority(
                        platform.buckets.open_stack_s3_endpoint
                    ),
                    "region": platform.buckets.open_stack_region_name,
                    "access_key": platform.buckets.open_stack_username,
                    "secret_key": platform.buckets.open_stack_password,
                },
            }
            prometheus_spec["thanos"] = {
                "objectStorageConfig": {"secret": result["thanos"]["objstore"]}
            }
        else:
            raise AssertionError("was unable to construct thanos object store config")
        if platform.kubernetes_provider == CloudProviderType.GCP:
            result["cloudProvider"] = {
                "type": "gcp",
                "region": platform.monitoring.metrics_region,
                "serviceAccountSecret": {
                    "name": f"{platform.release_name}-reports-gcp-key",
                    "key": "key.json",
                },
            }
        if platform.kubernetes_provider == CloudProviderType.AWS:
            result["cloudProvider"] = {
                "type": "aws",
                "region": platform.monitoring.metrics_region,
            }
        if platform.kubernetes_provider == CloudProviderType.AZURE:
            result["cloudProvider"] = {
                "type": "azure",
                "region": platform.monitoring.metrics_region,
            }
        return result

    def _relabel_reports_label(
        self, source_label: str, target_label: str
    ) -> dict[str, Any] | None:
        if source_label == target_label:
            return None
        return {
            "sourceLabels": [self._convert_label_to_reports_value(source_label)],
            "targetLabel": self._convert_label_to_reports_value(target_label),
        }

    def _convert_label_to_reports_value(self, value: str) -> str:
        return "label_" + value.replace(".", "_").replace("/", "_").replace("-", "_")

    def _get_url_authority(self, url: URL) -> str:
        assert url.is_absolute(), "Absolute url is required"
        assert url.host
        return url.host if url.is_default_port() else f"{url.host}:{url.port}"

    def create_platform_disks_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-disks",
            "fullnameOverride": f"{platform.release_name}-disks",
            "image": {"repository": platform.get_image("platformdiskapi")},
            "disks": {
                "namespace": platform.jobs_namespace,
                "limitPerUser": str(platform.disks_storage_limit_per_user),
            },
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
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
                "hosts": [platform.ingress_url.host],
            },
            "priorityClassName": platform.services_priority_class_name,
        }
        if platform.disks_storage_class_name:
            result["disks"]["storageClassName"] = platform.disks_storage_class_name
        result.update(**self._create_tracing_values(platform))
        return result

    def create_platform_api_poller_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-api-poller",
            "fullnameOverride": f"{platform.release_name}-api-poller",
            "image": {"repository": platform.get_image("platformapi")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_url_value(
                    "configUrl", platform.config_url, "api/v1"
                ),
                **self._create_platform_url_value(
                    "adminUrl", platform.admin_url, "apis/admin/v1"
                ),
                **self._create_platform_url_value("apiUrl", platform.api_url, "api/v1"),
                **self._create_platform_url_value(
                    "registryUrl", platform.ingress_registry_url
                ),
                **self._create_platform_token_value(platform),
            },
            "jobs": {
                "namespace": platform.jobs_namespace,
                "ingressClass": "traefik",
                "ingressAuthMiddleware": (
                    f"{platform.namespace}-{platform.release_name}-ingress-auth"
                    "@kubernetescrd"
                ),
                "ingressErrorPageMiddleware": (
                    f"{platform.namespace}-{platform.release_name}-error-page"
                    "@kubernetescrd"
                ),
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
            "ingress": {
                "enabled": True,
                "ingressClassName": "traefik",
                "hosts": [platform.ingress_url.host],
            },
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        if platform.kubernetes_provider == CloudProviderType.AZURE:
            result["jobs"][
                "preemptibleTolerationKey"
            ] = "kubernetes.azure.com/scalesetpriority"
        if platform.docker_hub_config:
            result["jobs"]["imagePullSecret"] = platform.docker_hub_config.secret_name
        return result

    def create_platform_buckets_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-buckets",
            "fullnameOverride": f"{platform.release_name}-buckets",
            "image": {"repository": platform.get_image("platformbucketsapi")},
            "bucketNamespace": platform.jobs_namespace,
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
            },
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
                "hosts": [platform.ingress_url.host],
            },
            "secrets": [],
            "disableCreation": platform.buckets.disable_creation,
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        if platform.buckets.provider == BucketsProvider.AWS:
            result["bucketProvider"] = {
                "type": "aws",
                "aws": {
                    "regionName": platform.buckets.aws_region,
                    "s3RoleArn": platform.aws_s3_role_arn,
                },
            }
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            secret_name = f"{platform.release_name}-buckets-emc-ecs-key"
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
            secret_name = f"{platform.release_name}-buckets-open-stack-key"
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
            secret_name = f"{platform.release_name}-buckets-azure-storage-account-key"
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
            secret_name = f"{platform.release_name}-buckets-gcp-sa-key"
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
            raise AssertionError("was unable to construct bucket provider")
        return result
