from __future__ import annotations

import base64
import textwrap
from hashlib import sha256
from typing import Any

import bcrypt
from neuro_config_client import ACMEEnvironment, CloudProviderType, IdleJobConfig
from yarl import URL

from .models import (
    BucketsProvider,
    DockerRegistryStorageDriver,
    HelmChartNames,
    IngressServiceType,
    LabelsConfig,
    MetricsStorageType,
    PlatformConfig,
    RegistryProvider,
    StorageConfig,
    StorageType,
)

PLATFORM_NEURO_JOB_TAINT_KEY = "platform.neuromation.io/job"
PLATFORM_APOLO_WORKER_TAINT_KEY = "platform.apolo.us/worker"


def b64encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


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
            "appsPostgresOperatorEnabled": (
                platform.apps_operator_config.postgres_operator_enabled
            ),
            "appsSparkOperatorEnabled": (
                platform.apps_operator_config.spark_operator_enabled
            ),
            "appsKedaEnabled": platform.apps_operator_config.keda_enabled,
            "minioEnabled": platform.buckets.minio_install,
            "minioGatewayEnabled": platform.minio_gateway is not None,
            "platformReportsEnabled": platform.monitoring.metrics_enabled,
            "lokiEnabled": platform.monitoring.loki_enabled,
            "alloyEnabled": platform.monitoring.alloy_enabled,
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
                    "nvidiaGpu": rpt.nvidia_gpu or 0,
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
            self._chart_names.platform_apps: self.create_platform_apps_values(platform),
            self._chart_names.platform_metadata: self.create_platform_metadata_values(
                platform
            ),
            self._chart_names.spark_operator: self.create_spark_operator_values(
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
            result[self._chart_names.docker_registry] = (
                self.create_docker_registry_values(platform)
            )
        if platform.buckets.minio_install:
            assert platform.buckets.minio_public_url
            result["ingress"]["minioHost"] = platform.buckets.minio_public_url.host
            result[self._chart_names.minio] = self.create_minio_values(platform)
        if platform.minio_gateway is not None:
            result[self._chart_names.minio_gateway] = self.create_minio_gateway_values(
                platform
            )
        if platform.monitoring.metrics_enabled:
            result[self._chart_names.platform_reports] = (
                self.create_platform_reports_values(platform)
            )
            result["alertmanager"] = self._create_alert_manager_values(platform)
        if platform.monitoring.loki_enabled:
            result[self._chart_names.loki] = self.create_loki_values(platform)
        if platform.monitoring.alloy_enabled:
            result[self._chart_names.alloy] = self.create_alloy_values(platform)
        return result

    def _create_alert_manager_values(self, platform: PlatformConfig) -> dict[str, Any]:
        if platform.notifications_url == URL("-"):
            return {}
        return {
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
                            "matchers": [
                                f'exported_service=~"{platform.jobs_namespace}-.+"'
                            ],
                            "continue": False,
                        },
                        {
                            "receiver": "ignore",
                            "matchers": [f'namespace="{platform.jobs_namespace}"'],
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
                                "url": str(
                                    platform.notifications_url
                                    / "api/v1/notifications"
                                    / "alert-manager-notification"
                                ),
                                "http_config": {
                                    "authorization": {
                                        "type": "Bearer",
                                        "credentials_file": (
                                            "/etc/alertmanager/secrets"
                                            f"/{platform.release_name}-token/token"
                                        ),
                                    }
                                },
                            }
                        ],
                    },
                ],
            }
        }

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
                    f"*.apps.{platform.ingress_url.host}",
                ],
                "sslCertSecretName": f"{platform.release_name}-ssl-cert",
            },
            "podLabels": {"service": "acme"},
            "env": [
                {"name": "NEURO_URL", "value": str(platform.auth_url)},
                {"name": "NEURO_CLUSTER", "value": platform.cluster_name},
                {
                    "name": "NEURO_TOKEN",
                    **self._create_value_from_secret(
                        name=f"{platform.release_name}-token", key="token"
                    ),
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
                "cpu": f"{round(job.resources.cpu * 1000)}m",
                "memory": f"{job.resources.memory}",
            },
        }
        if job.command:
            result["command"] = job.command
        if job.args:
            result["args"] = job.args
        if job.image_pull_secret:
            result["imagePullSecrets"] = [{"name": job.image_pull_secret}]
        if job.resources.nvidia_gpu:
            result["resources"]["nvidia.com/gpu"] = job.resources.nvidia_gpu
        if job.env:
            result["env"] = job.env
        if job.node_selector:
            result["nodeSelector"] = job.node_selector
        return result

    def _create_storage_values(self, storage: StorageConfig) -> dict[str, Any]:
        if storage.type == StorageType.NFS:
            return {
                "type": StorageType.NFS.value,
                "path": storage.path,
                "size": storage.size,
                "nfs": {
                    "server": storage.nfs_server,
                    "path": storage.nfs_export_path,
                },
            }
        if storage.type == StorageType.SMB:
            return {
                "type": StorageType.SMB.value,
                "path": storage.path,
                "size": storage.size,
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
                "size": storage.size,
                "azureFile": {
                    "storageAccountName": storage.azure_storage_account_name,
                    "storageAccountKey": storage.azure_storage_account_key,
                    "shareName": storage.azure_share_name,
                },
            }
        raise ValueError(f"Storage type {storage.type.value!r} is not supported")

    def create_docker_registry_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "image": {"repository": platform.get_image("registry")},
            "ingress": {"enabled": False},
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
        if (
            platform.registry.docker_registry_storage_driver
            == DockerRegistryStorageDriver.FILE_SYSTEM
        ):
            result["storage"] = "filesystem"
            result["persistence"] = {
                "enabled": True,
                "storageClass": (
                    platform.registry.docker_registry_file_system_storage_class_name
                ),
                "size": platform.registry.docker_registry_file_system_storage_size,
            }
        elif (
            platform.registry.docker_registry_storage_driver
            == DockerRegistryStorageDriver.S3
        ):
            assert platform.registry.docker_registry_s3_endpoint
            result["replicaCount"] = 2
            result["storage"] = "s3"
            result["s3"] = {
                "region": platform.registry.docker_registry_s3_region,
                "regionEndpoint": self._get_url_authority(
                    platform.registry.docker_registry_s3_endpoint
                ),
                "bucket": str(platform.registry.docker_registry_s3_bucket),
            }
            result["secrets"]["s3"] = {
                "accessKey": platform.registry.docker_registry_s3_access_key,
                "secretKey": platform.registry.docker_registry_s3_secret_key,
            }
            result["configData"]["storage"]["s3"] = {
                "secure": platform.registry.docker_registry_s3_endpoint.scheme
                == "https",
                "forcepathstyle": platform.registry.docker_registry_s3_force_path_style,
            }
            result["configData"]["storage"]["redirect"] = {
                "disable": platform.registry.docker_registry_s3_disable_redirect
            }
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

    def create_minio_gateway_values(self, platform: PlatformConfig) -> dict[str, Any]:
        assert platform.minio_gateway
        result = {
            "nameOverride": "minio-gateway",
            "fullnameOverride": "minio-gateway",
            "replicaCount": 2,
            "image": {"repository": platform.get_image("minio")},
            "imagePullSecrets": [
                {"name": name} for name in platform.image_pull_secret_names
            ],
            "rootUser": {
                "user": platform.minio_gateway.root_user,
                "password": platform.minio_gateway.root_user_password,
            },
        }
        if platform.buckets.provider == BucketsProvider.GCP:
            result["cloudStorage"] = {
                "type": "gcs",
                "gcs": {"project": platform.buckets.gcp_project},
            }
            result["env"] = [
                {
                    "name": "GOOGLE_APPLICATION_CREDENTIALS",
                    "value": "/etc/config/minio/gcs/key.json",
                }
            ]
            result["secrets"] = [
                {
                    "name": "minio-gateway-gcs-key",
                    "data": {"key.json": platform.gcp_service_account_key},
                }
            ]
            result["volumes"] = [
                {
                    "name": "gcp-credentials",
                    "secret": {
                        "secretName": "minio-gateway-gcs-key",
                        "optional": False,
                    },
                }
            ]
            result["volumeMounts"] = [
                {
                    "name": "gcp-credentials",
                    "mountPath": "/etc/config/minio/gcs",
                    "readOnly": True,
                }
            ]
        elif platform.buckets.provider == BucketsProvider.AZURE:
            result["cloudStorage"] = {"type": "azure"}
        else:
            raise ValueError(
                f"Buckets provider {platform.buckets.provider} not supported"
            )
        return result

    def create_traefik_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": "traefik",
            "fullnameOverride": "traefik",
            "instanceLabelOverride": platform.release_name,
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
                "web": {"redirectTo": {"port": "websecure"}},
                "websecure": {"tls": {"enabled": True}},
            },
            "additionalArguments": [
                "--entryPoints.websecure.proxyProtocol.insecure=true",
                "--entryPoints.websecure.forwardedHeaders.insecure=true",
                "--entryPoints.websecure.http.middlewares="
                f"{platform.namespace}-{platform.release_name}-cors@kubernetescrd",
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
                    # published service conflicts with ingressendpoint.ip arg
                    "publishedService": {"enabled": False},
                },
            },
            "tlsStore": {
                "default": {
                    "defaultCertificate": {
                        "secretName": f"{platform.release_name}-ssl-cert"
                    },
                }
            },
            "ingressRoute": {"dashboard": {"enabled": False}},
            "logs": {"general": {"level": "ERROR"}},
            "priorityClassName": platform.services_priority_class_name,
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
            ports = result["ports"]
            if platform.ingress_node_port_http and platform.ingress_node_port_https:
                ports["web"]["nodePort"] = platform.ingress_node_port_http
                ports["websecure"]["nodePort"] = platform.ingress_node_port_https
            if platform.ingress_host_port_http and platform.ingress_host_port_https:
                result["updateStrategy"] = {
                    "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0}
                }
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
                    **self._create_value_from_secret(
                        name=f"{platform.release_name}-token", key="token"
                    ),
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

    def _create_value_from_secret(self, *, name: str, key: str) -> dict[str, Any]:
        result = {"valueFrom": {"secretKeyRef": {"name": name, "key": key}}}
        return result

    def create_platform_storage_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-storage",
            "fullnameOverride": f"{platform.release_name}-storage",
            "image": {"repository": platform.get_image("platformstorageapi")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_url_value("adminUrl", platform.admin_url),
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
            "storageUsageCollector": {
                "resources": {
                    "requests": {"cpu": "250m", "memory": "500Mi"},
                    "limits": {"cpu": "1000m", "memory": "1Gi"},
                }
            },
            "secrets": [],
        }
        result.update(**self._create_tracing_values(platform))
        s3_secret_name = f"{platform.release_name}-storage-s3"
        if platform.buckets.provider == BucketsProvider.GCP:
            assert platform.minio_gateway
            result["secrets"].append(
                {
                    "name": s3_secret_name,
                    "data": {
                        "access_key_id": platform.minio_gateway.root_user,
                        "secret_access_key": platform.minio_gateway.root_user_password,
                    },
                }
            )
            result["s3"] = {
                "endpoint": "http://minio-gateway:9000",
                "region": (
                    platform.monitoring.logs_region or platform.buckets.gcp_location
                ),
                "accessKeyId": self._create_value_from_secret(
                    name=s3_secret_name, key="access_key_id"
                ),
                "secretAccessKey": self._create_value_from_secret(
                    name=s3_secret_name, key="secret_access_key"
                ),
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        elif platform.buckets.provider == BucketsProvider.AZURE:
            assert platform.minio_gateway
            result["secrets"].append(
                {
                    "name": s3_secret_name,
                    "data": {
                        "access_key_id": platform.minio_gateway.root_user,
                        "secret_access_key": platform.minio_gateway.root_user_password,
                    },
                }
            )
            result["s3"] = {
                "endpoint": "http://minio-gateway:9000",
                "region": "minio",
                "accessKeyId": self._create_value_from_secret(
                    name=s3_secret_name, key="access_key_id"
                ),
                "secretAccessKey": self._create_value_from_secret(
                    name=s3_secret_name, key="secret_access_key"
                ),
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        elif platform.buckets.provider == BucketsProvider.AWS:
            result["s3"] = {
                "region": platform.buckets.aws_region,
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        elif platform.buckets.provider == BucketsProvider.EMC_ECS:
            result["secrets"].append(
                {
                    "name": s3_secret_name,
                    "data": {
                        "access_key_id": platform.buckets.emc_ecs_access_key_id,
                        "secret_access_key": platform.buckets.emc_ecs_secret_access_key,
                    },
                }
            )
            result["s3"] = {
                "endpoint": str(platform.buckets.emc_ecs_s3_endpoint),
                "region": "emc-ecs",
                "accessKeyId": self._create_value_from_secret(
                    name=s3_secret_name, key="access_key_id"
                ),
                "secretAccessKey": self._create_value_from_secret(
                    name=s3_secret_name, key="secret_access_key"
                ),
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
            result["secrets"].append(
                {
                    "name": s3_secret_name,
                    "data": {
                        "access_key_id": platform.buckets.open_stack_username,
                        "secret_access_key": platform.buckets.open_stack_password,
                    },
                }
            )
            result["s3"] = {
                "endpoint": str(platform.buckets.open_stack_s3_endpoint),
                "region": platform.buckets.open_stack_region_name,
                "accessKeyId": self._create_value_from_secret(
                    name=s3_secret_name, key="access_key_id"
                ),
                "secretAccessKey": self._create_value_from_secret(
                    name=s3_secret_name, key="secret_access_key"
                ),
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        elif platform.buckets.provider == BucketsProvider.MINIO:
            result["secrets"].append(
                {
                    "name": s3_secret_name,
                    "data": {
                        "access_key_id": platform.buckets.minio_access_key,
                        "secret_access_key": platform.buckets.minio_secret_key,
                    },
                }
            )
            result["s3"] = {
                "endpoint": str(platform.buckets.minio_url),
                "region": platform.buckets.minio_region,
                "accessKeyId": self._create_value_from_secret(
                    name=s3_secret_name, key="access_key_id"
                ),
                "secretAccessKey": self._create_value_from_secret(
                    name=s3_secret_name, key="secret_access_key"
                ),
                "bucket": platform.monitoring.metrics_bucket_name,
                "keyPrefix": "storage/",
            }
        else:
            raise ValueError(
                f"Bucket provider {platform.buckets.provider} not supported"
            )
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
                    **self._create_value_from_secret(
                        name=gcp_key_secret_name, key="username"
                    ),
                },
                "tokenPassword": {
                    **self._create_value_from_secret(
                        name=gcp_key_secret_name, key="password"
                    ),
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
                    **self._create_value_from_secret(
                        name=azure_credentials_secret_name, key="username"
                    ),
                },
                "tokenPassword": {
                    **self._create_value_from_secret(
                        name=azure_credentials_secret_name, key="password"
                    ),
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
                    **self._create_value_from_secret(
                        name=docker_registry_credentials_secret_name, key="username"
                    ),
                },
                "basicPassword": {
                    **self._create_value_from_secret(
                        name=docker_registry_credentials_secret_name, key="password"
                    ),
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
                "nodePool": platform.node_labels.node_pool,
            },
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_url_value("configUrl", platform.config_url),
                **self._create_platform_url_value("apiUrl", platform.api_url),
                **self._create_platform_url_value("appsUrl", platform.api_url),
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
            "priorityClassName": platform.services_priority_class_name,
            "logs": {
                "persistence": {
                    "type": "loki",
                    "loki": {
                        "endpoint": self._create_loki_endpoint(platform),
                        "archiveDelay": "5",
                        "retentionPeriodS": "2592000",  # 30 days
                    },
                },
            },
        }
        result.update(**self._create_tracing_values(platform))
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
                **self._create_platform_url_value("apiUrl", platform.api_url),
                **self._create_platform_token_value(platform),
            },
            "secrets": [],
            "platformJobs": {"namespace": platform.jobs_namespace},
            "metricsApi": {
                "ingress": {
                    "enabled": True,
                    "ingressClassName": "traefik",
                    "hosts": [platform.ingress_url.host],
                }
            },
            "grafanaProxy": {
                "ingress": {
                    "enabled": True,
                    "ingressClassName": "traefik",
                    "hosts": [
                        platform.ingress_grafana_url.host,
                        platform.ingress_metrics_url.host,  # deprecated
                    ],
                    "annotations": {
                        "traefik.ingress.kubernetes.io/router.middlewares": (
                            f"{platform.namespace}-{platform.release_name}-ingress-auth"
                            "@kubernetescrd"
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
                    "enabled": platform.monitoring.metrics_node_exporter_enabled,
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
                "alertmanager": {
                    "alertmanagerSpec": {
                        "image": {
                            "registry": platform.image_registry,
                            "repository": platform.get_image_repo("alertmanager"),
                        },
                        "configSecret": f"{platform.release_name}-alertmanager-config",
                        "secrets": [f"{platform.release_name}-token"],
                    }
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
                "sidecar": {"selector": {"app": None}},
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
            result["prometheus"]["url"] = "http://prometheus-prometheus:9090"
            result["prometheus"]["remoteStorageEnabled"] = False
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
                    "service_account": platform.gcp_service_account_key,
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
                    "insecure": platform.buckets.minio_url.scheme == "http",
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
                        **self._create_value_from_secret(name=secret_name, key="key"),
                    },
                    "secretAccessKey": {
                        **self._create_value_from_secret(
                            name=secret_name, key="secret"
                        ),
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
                        **self._create_value_from_secret(
                            name=secret_name, key="accountId"
                        ),
                    },
                    "password": {
                        **self._create_value_from_secret(
                            name=secret_name, key="password"
                        ),
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
                        **self._create_value_from_secret(name=secret_name, key="key"),
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
                        **self._create_value_from_secret(
                            name=secret_name, key="SAKeyB64"
                        ),
                    }
                },
            }
        else:
            raise AssertionError("was unable to construct bucket provider")
        return result

    def create_platform_apps_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-apps",
            "fullnameOverride": f"{platform.release_name}-apps",
            "image": {"repository": platform.get_image("platform-apps")},
            "platform": {
                "clusterName": platform.cluster_name,
                **self._create_platform_url_value("authUrl", platform.auth_url),
                **self._create_platform_token_value(platform),
            },
            "ingress": {
                "enabled": True,
                "className": "traefik",
                "hosts": [platform.ingress_url.host],
            },
            "priorityClassName": platform.services_priority_class_name,
            "rbac": {"create": True},
            "serviceAccount": {"create": True},
        }
        result.update(**self._create_tracing_values(platform))
        return result

    def create_loki_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": "loki",
            "fullnameOverride": "loki",
            "global": {
                "dnsService": platform.monitoring.loki_dns_service,
            },
            "deploymentMode": "SimpleScalable",
            "loki": {
                "commonConfig": {"replication_factor": 1},
                "auth_enabled": False,
            },
            "test": {"enabled": False},
            "lokiCanary": {"enabled": False},
            "resultsCache": {"allocatedMemory": 512},
            "chunksCache": {"allocatedMemory": 2048},
            "ingester": {"chunk_encoding": "snappy"},
            "table_manager": {
                "retention_deletes_enabled": True,
                "retention_period": "2160h",
            },
            "query_scheduler": {
                "max_outstanding_requests_per_tenant": 32768,
            },
            "querier": {
                "max_concurrent": 4,  # Default is 4, adjust based on memory and CPU
            },
            "pattern_ingester": {
                "enabled": True,
            },
            "limits_config": {
                "allow_structured_metadata": True,
                "volume_enabled": True,
                "retention_period": "90d",
            },
            "minio": {"enabled": False},
            "gateway": {
                "replicas": 1,
                "resources": {
                    "requests": {"memory": "100Mi", "cpu": "10m"},
                    "limits": {"memory": "100Mi"},
                },
            },
            "write": {
                "replicas": 1,
                "resources": {
                    "requests": {"memory": "512Mi", "cpu": "100m"},
                    "limits": {"memory": "1024Mi"},
                },
            },
            "read": {
                "replicas": 1,
                "resources": {
                    "requests": {"memory": "100Mi", "cpu": "100m"},
                    "limits": {"memory": "2048Mi"},
                },
            },
            "backend": {
                "replicas": 1,
                "resources": {
                    "requests": {"memory": "100Mi", "cpu": "100m"},
                    "limits": {"memory": "512Mi", "cpu": "100m"},
                },
            },
        }

        bucket_name = platform.monitoring.logs_bucket_name
        if platform.buckets.provider == BucketsProvider.GCP:
            loki_gcs_key_secret_name = "loki-gcs-key"
            result["extraObjects"] = [
                textwrap.dedent(
                    f"""
                    apiVersion: v1
                    kind: Secret
                    type: Opaque
                    metadata:
                      name: {loki_gcs_key_secret_name}
                      namespace: {platform.namespace}
                    data:
                      key.json: {platform.gcp_service_account_key_base64}
                    """
                )
            ]

            extra_env = {
                "extraEnv": [
                    {
                        "name": "GOOGLE_APPLICATION_CREDENTIALS",
                        "value": "/etc/secrets/key.json",
                    }
                ],
                "extraVolumes": [
                    {
                        "name": "loki-access-gcs",
                        "secret": {
                            "secretName": loki_gcs_key_secret_name,
                        },
                    }
                ],
                "extraVolumeMounts": [
                    {
                        "name": "loki-access-gcs",
                        "mountPath": "/etc/secrets",
                    }
                ],
            }

            result["loki"].update(
                {
                    "storage": {
                        "bucketNames": {
                            "chunks": bucket_name,
                            "ruler": bucket_name,
                            "admin": bucket_name,
                        },
                        "type": "gcs",
                    },
                    "schemaConfig": {
                        "configs": [
                            {
                                "from": "2025-01-01",
                                "object_store": "gcs",
                                "store": "tsdb",
                                "schema": "v13",
                                "index": {"prefix": "index_", "period": "24h"},
                            }
                        ]
                    },
                }
            )
            result["write"].update(extra_env)
            result["read"].update(extra_env)
            result["backend"].update(extra_env)

        elif platform.buckets.provider == BucketsProvider.AZURE:
            result["loki"].update(
                {
                    "rulerConfig": {
                        "storage": {
                            "type": "azure",
                            "azure": {
                                "account_key": (
                                    platform.buckets.azure_storage_account_key
                                ),
                                "account_name": (
                                    platform.buckets.azure_storage_account_name
                                ),
                                "container_name": bucket_name,
                                "use_managed_identity": False,
                                "request_timeout": 0,
                            },
                        }
                    },
                    "schemaConfig": {
                        "configs": [
                            {
                                "from": "2025-01-01",
                                "object_store": "azure",
                                "store": "tsdb",
                                "schema": "v13",
                                "index": {"prefix": "index_", "period": "24h"},
                            }
                        ]
                    },
                    "storage": {
                        "bucketNames": {
                            "chunks": bucket_name,
                            "ruler": bucket_name,
                            "admin": bucket_name,
                        },
                        "type": "azure",
                    },
                    "storage_config": {
                        "azure": {
                            "account_key": platform.buckets.azure_storage_account_key,
                            "account_name": platform.buckets.azure_storage_account_name,
                            "container_name": bucket_name,
                            "use_managed_identity": False,
                            "request_timeout": 0,
                        }
                    },
                }
            )

        elif platform.buckets.provider == BucketsProvider.AWS:
            result["serviceAccount"] = {
                "create": False,
                "name": platform.service_account_name,
            }
            result["loki"].update(
                {
                    "rulerConfig": {
                        "storage": {
                            "type": "s3",
                            "s3": {
                                "bucketnames": bucket_name,
                                "region": platform.buckets.aws_region,
                                "insecure": False,
                            },
                        }
                    },
                    "schemaConfig": {
                        "configs": [
                            {
                                "from": "2025-01-01",
                                "object_store": "s3",
                                "store": "tsdb",
                                "schema": "v13",
                                "index": {"prefix": "index_", "period": "24h"},
                            }
                        ]
                    },
                    "storage": {
                        "bucketNames": {
                            "chunks": bucket_name,
                            "ruler": bucket_name,
                            "admin": bucket_name,
                        },
                        "type": "s3",
                    },
                    "storage_config": {
                        "aws": {
                            "bucketnames": bucket_name,
                            "region": platform.buckets.aws_region,
                            "insecure": False,
                        }
                    },
                }
            )

        elif platform.buckets.provider in [
            BucketsProvider.MINIO,
            BucketsProvider.EMC_ECS,
            BucketsProvider.OPEN_STACK,
        ]:
            if platform.buckets.provider == BucketsProvider.MINIO:
                s3_endpoint_url = str(platform.buckets.minio_url)
                s3_region = platform.buckets.minio_region
                s3_access_key_id = platform.buckets.minio_access_key
                s3_secret_access_key = platform.buckets.minio_secret_key
            elif platform.buckets.provider == BucketsProvider.EMC_ECS:
                s3_endpoint_url = str(platform.buckets.emc_ecs_s3_endpoint)
                s3_region = platform.buckets.emc_ecs_region
                s3_access_key_id = platform.buckets.emc_ecs_access_key_id
                s3_secret_access_key = platform.buckets.emc_ecs_secret_access_key
            elif platform.buckets.provider == BucketsProvider.OPEN_STACK:
                s3_endpoint_url = str(platform.buckets.open_stack_s3_endpoint)
                s3_region = platform.buckets.open_stack_region_name
                s3_access_key_id = platform.buckets.open_stack_username
                s3_secret_access_key = platform.buckets.open_stack_password

            loki_s3_key_secret_name = "loki-s3-key"
            result["extraObjects"] = [
                textwrap.dedent(
                    f"""
                    apiVersion: v1
                    kind: Secret
                    type: Opaque
                    metadata:
                      name: {loki_s3_key_secret_name}
                      namespace: {platform.namespace}
                    data:
                      access_key_id: {b64encode(s3_access_key_id)}
                      secret_access_key: {b64encode(s3_secret_access_key)}
                    """
                )
            ]
            extra_env = {
                "extraArgs": ["-config.expand-env=true"],
                "extraEnv": [
                    {
                        "name": "LOKI_S3_ACCESS_KEY_ID",
                        **self._create_value_from_secret(
                            name=loki_s3_key_secret_name, key="access_key_id"
                        ),
                    },
                    {
                        "name": "LOKI_S3_SECRET_ACCESS_KEY",
                        **self._create_value_from_secret(
                            name=loki_s3_key_secret_name, key="secret_access_key"
                        ),
                    },
                ],
            }
            result["write"].update(extra_env)
            result["read"].update(extra_env)
            result["backend"].update(extra_env)

            result["loki"].update(
                {
                    "rulerConfig": {
                        "storage": {
                            "type": "s3",
                            "s3": {
                                "endpoint": s3_endpoint_url,
                                "bucketnames": bucket_name,
                                "region": s3_region,
                                "access_key_id": "${LOKI_S3_ACCESS_KEY_ID}",
                                "secret_access_key": "${LOKI_S3_SECRET_ACCESS_KEY}",
                                "insecure": False,
                                "s3forcepathstyle": True,
                            },
                        }
                    },
                    "schemaConfig": {
                        "configs": [
                            {
                                "from": "2025-01-01",
                                "object_store": "s3",
                                "store": "tsdb",
                                "schema": "v13",
                                "index": {"prefix": "index_", "period": "24h"},
                            }
                        ]
                    },
                    "storage": {
                        "bucketNames": {
                            "chunks": bucket_name,
                            "ruler": bucket_name,
                            "admin": bucket_name,
                        },
                        "type": "s3",
                    },
                    "storage_config": {
                        "aws": {
                            "endpoint": s3_endpoint_url,
                            "bucketnames": bucket_name,
                            "region": s3_region,
                            "access_key_id": "${LOKI_S3_ACCESS_KEY_ID}",
                            "secret_access_key": "${LOKI_S3_SECRET_ACCESS_KEY}",
                            "insecure": False,
                            "s3forcepathstyle": True,
                        }
                    },
                }
            )

        else:
            raise ValueError("Bucket provider is not supported")

        return result

    def _create_loki_endpoint(self, platform: PlatformConfig) -> str:
        if platform.monitoring.loki_enabled:
            return f"http://loki-gateway.{platform.namespace}"
        return platform.monitoring.loki_endpoint

    def create_alloy_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": "alloy",
            "fullnameOverride": "alloy",
            "alloy": {
                "configMap": {
                    "create": True,
                    "content": textwrap.dedent(
                        r"""
                        loki.write "default" {
                          endpoint {
                            url = "http://loki-gateway.{$namespace}.svc.cluster.local/loki/api/v1/push"
                          }
                        }

                        discovery.kubernetes "kubernetes_pods" {
                          role = "pod"

                          selectors {
                            role = "pod"
                            field = "spec.nodeName=" + coalesce(env("HOSTNAME"), constants.hostname)
                          }
                        }

                        discovery.relabel "kubernetes_pods" {
                          targets = discovery.kubernetes.kubernetes_pods.targets

                          rule {
                            source_labels = ["__meta_kubernetes_pod_controller_name"]
                            regex         = "([0-9a-z-.]+?)(-[0-9a-f]{8,10})?"
                            target_label  = "__tmp_controller_name"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_name", "__meta_kubernetes_pod_label_app", "__tmp_controller_name", "__meta_kubernetes_pod_name"]
                            regex         = "^;*([^;]+)(;.*)?$"
                            target_label  = "app"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_instance", "__meta_kubernetes_pod_label_instance"]
                            regex         = "^;*([^;]+)(;.*)?$"
                            target_label  = "instance"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_app_kubernetes_io_component", "__meta_kubernetes_pod_label_component"]
                            regex         = "^;*([^;]+)(;.*)?$"
                            target_label  = "component"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_node_name"]
                            target_label  = "node_name"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_namespace"]
                            target_label  = "namespace"
                          }

                          rule {
                            source_labels = ["namespace", "app"]
                            separator     = "/"
                            target_label  = "job"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_name"]
                            target_label  = "pod"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_container_name"]
                            target_label  = "container"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_uid", "__meta_kubernetes_pod_container_name"]
                            separator     = "/"
                            target_label  = "__path__"
                            replacement   = "/var/log/pods/*$1/*.log"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_annotationpresent_kubernetes_io_config_hash", "__meta_kubernetes_pod_annotation_kubernetes_io_config_hash", "__meta_kubernetes_pod_container_name"]
                            separator     = "/"
                            regex         = "true/(.*)"
                            target_label  = "__path__"
                            replacement   = "/var/log/pods/*$1/*.log"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_platform_apolo_us_org"]
                            target_label  = "apolo_org_name"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_platform_apolo_us_project"]
                            target_label  = "apolo_project_name"
                          }

                          rule {
                            source_labels = ["__meta_kubernetes_pod_label_platform_apolo_us_app"]
                            target_label  = "apolo_app_id"
                          }
                        }

                        loki.process "kubernetes_pods" {
                          forward_to = [loki.write.default.receiver]

                          stage.cri { }

                          stage.replace {
                            expression = "(\\n)"
                          }

                          stage.decolorize {}

                          stage.multiline {
                            firstline = "^\\S+.*"
                            max_lines = 0
                          }

                          stage.match {
                            selector = "{pod=~\".+\"} |~ \"^\\\\d{4}-\\\\d{2}-\\\\d{2}T\\\\d{2}:\\\\d{2}:\\\\d{2}(?:\\\\.\\\\d+)?Z?\\\\s+\\\\S+\\\\s+\\\\S+\\\\s+(?:\\\\[[^\\\\]]*\\\\])?\\\\s+.*\""

                            stage.regex {
                              expression = "(?s)(?P<timestamp>\\S+)\\s+(?P<level>\\S+)\\s+(?P<logger>\\S+)\\s+(?:\\[(?P<context>[^\\]]*)\\])?\\s+(?P<message>.*)"
                            }

                            stage.timestamp {
                              source = "timestamp"
                              format = "RFC3339"
                            }

                            stage.labels {
                              values = {
                                context = "",
                                level   = "",
                                logger  = "",
                              }
                            }

                            stage.structured_metadata {
                              values = {
                                level   = "",
                              }
                            }

                            stage.output {
                              source = "message"
                            }
                          }

                          stage.pack {
                            labels           = ["stream", "node_name", "level", "logger", "context"]
                            ingest_timestamp = false
                          }

                          stage.label_keep {
                            values = ["app", "instance", "namespace", "pod", "container", "apolo_org_name", "apolo_project_name", "apolo_app_id"]
                          }
                        }

                        loki.source.kubernetes "kubernetes_pods" {
                          targets    = discovery.relabel.kubernetes_pods.output
                          forward_to = [loki.process.kubernetes_pods.receiver]
                        }
                    """  # noqa: E501
                    ),
                }
            },
            "controller": {
                "tolerations": [
                    {
                        "key": PLATFORM_APOLO_WORKER_TAINT_KEY,
                        "effect": "NoSchedule",
                        "operator": "Exists",
                    },
                    {
                        "key": PLATFORM_NEURO_JOB_TAINT_KEY,
                        "effect": "NoSchedule",
                        "operator": "Exists",
                    },
                ]
            },
        }
        result["alloy"]["configMap"]["content"] = result["alloy"]["configMap"][
            "content"
        ].replace("{$namespace}", platform.namespace)
        return result

    def create_platform_metadata_values(
        self, platform: PlatformConfig
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "nameOverride": f"{platform.release_name}-metadata",
            "fullnameOverride": f"{platform.release_name}-metadata",
            "image": {"repository": platform.get_image("platform-metadata")},
            "priorityClassName": platform.services_priority_class_name,
        }
        result.update(**self._create_tracing_values(platform))
        return result

    def create_spark_operator_values(self, platform: PlatformConfig) -> dict[str, Any]:
        result: dict[str, Any] = {"spark": {"jobNamespaces": None}}
        return result
