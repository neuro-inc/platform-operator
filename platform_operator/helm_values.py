from base64 import b64decode
from hashlib import sha256
from typing import Any, Dict, Optional

import bcrypt

from .models import (
    HelmChartNames,
    HelmReleaseNames,
    LabelsConfig,
    PlatformConfig,
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
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "tags": {platform.cloud_provider: True},
            "traefikEnabled": platform.ingress_controller_install,
            "consulEnabled": platform.consul_install,
            "alpineImage": {"repository": f"{docker_server}/alpine"},
            "pauseImage": {"repository": f"{docker_server}/google_containers/pause"},
            "crictlImage": {"repository": f"{docker_server}/crictl"},
            "serviceToken": platform.token,
            "kubernetes": {
                "nodePools": platform.jobs_node_pools,
                "labels": {
                    "nodePool": platform.kubernetes_node_labels.node_pool,
                    "job": platform.kubernetes_node_labels.job,
                },
                "imagesPrepull": {
                    "refreshInterval": "1h",
                    "images": [{"image": image} for image in platform.pre_pull_images],
                },
            },
            "standardStorageClass": {
                "create": not platform.on_prem,
                "name": platform.standard_storage_class_name,
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
                "label": platform.kubernetes_node_labels.job,
            },
            "idleJobs": [self._create_idle_job(job) for job in platform.idle_jobs],
            "storages": [self._create_storage_values(s) for s in platform.storages],
            "disks": {
                "storageClass": {
                    "create": not platform.on_prem,
                    "name": platform.disks_storage_class_name,
                }
            },
            self._chart_names.adjust_inotify: self.create_adjust_inotify_values(
                platform
            ),
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
        if platform.docker_config_secret_create:
            result["dockerConfigSecret"] = {
                "create": True,
                "name": platform.docker_config_secret_name,
                "credentials": {
                    "url": str(platform.docker_registry.url),
                    "email": platform.docker_registry.email,
                    "username": platform.docker_registry.username,
                    "password": platform.docker_registry.password,
                },
            }
        else:
            result["dockerConfigSecret"] = {"create": False}
        if platform.docker_hub_registry:
            result["dockerHubConfigSecret"] = {
                "create": True,
                "name": platform.docker_hub_config_secret_name,
                "credentials": {
                    "url": str(platform.docker_hub_registry.url),
                    "email": platform.docker_hub_registry.email,
                    "username": platform.docker_hub_registry.username,
                    "password": platform.docker_hub_registry.password,
                },
            }
        else:
            result["dockerHubConfigSecret"] = {"create": False}
        if platform.consul_install:
            result[self._chart_names.consul] = self.create_consul_values(platform)
        if platform.gcp:
            result[
                self._chart_names.nvidia_gpu_driver_gcp
            ] = self.create_nvidia_gpu_driver_gcp_values(platform)
        else:
            result[
                self._chart_names.nvidia_gpu_driver
            ] = self.create_nvidia_gpu_driver_values(platform)
        if platform.aws:
            result[
                self._chart_names.cluster_autoscaler
            ] = self.create_cluster_autoscaler_values(platform)
        if platform.azure:
            result["blobStorage"] = {
                "azure": {
                    "storageAccountName": platform.azure.blob_storage_account_name,
                    "storageAccountKey": platform.azure.blob_storage_account_key,
                }
            }
        if platform.on_prem:
            result["tags"] = {"on_prem": True}
            result["dockerRegistryEnabled"] = platform.on_prem.docker_registry_install
            result["minioEnabled"] = platform.on_prem.minio_install
            if platform.on_prem.docker_registry_install:
                result[
                    self._chart_names.docker_registry
                ] = self.create_docker_registry_values(platform)
            if platform.on_prem.minio_install:
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
                "size": storage.storage_size,
                "storageClassName": storage.storage_class_name,
            }
        if storage.type == StorageType.NFS:
            return {
                "type": StorageType.NFS.value,
                "size": storage.storage_size,
                "nfs": {
                    "server": storage.nfs_server,
                    "path": storage.nfs_export_path,
                },
            }
        if storage.type == StorageType.AZURE_fILE:
            return {
                "type": StorageType.AZURE_fILE.value,
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
                "size": storage.storage_size,
                "gcs": {
                    "bucketName": storage.gcs_bucket_name,
                },
            }
        raise ValueError(f"Storage type {storage.type.value!r} is not supported")

    def create_obs_csi_driver_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.gcp
        return {
            "image": f"{platform.docker_registry.url.host}/obs-csi-driver",
            "driverName": "obs.csi.neu.ro",
            "credentialsSecret": {
                "create": True,
                "gcpServiceAccountKeyBase64": platform.gcp.service_account_key_base64,
            },
            "imagePullSecret": {
                "create": True,
                "credentials": {
                    "url": str(platform.docker_registry.url),
                    "email": platform.docker_registry.email,
                    "username": platform.docker_registry.username,
                    "password": platform.docker_registry.password,
                },
            },
        }

    def create_docker_registry_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        result: Dict[str, Any] = {
            "image": {"repository": f"{platform.docker_registry.url.host}/registry"},
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": platform.on_prem.registry_storage_class_name,
                "size": platform.on_prem.registry_storage_size,
            },
            "secrets": {
                "haSharedSecret": sha256(platform.cluster_name.encode()).hexdigest()
            },
        }
        if platform.on_prem.registry_username and platform.on_prem.registry_password:
            username = platform.on_prem.registry_username
            password_hash = bcrypt.hashpw(
                platform.on_prem.registry_password.encode(), bcrypt.gensalt(rounds=10)
            ).decode()
            result["secrets"]["htpasswd"] = f"{username}:{password_hash}"
        return result

    def create_minio_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        return {
            "image": {
                "repository": f"{platform.docker_registry.url.host}/minio/minio",
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
                "storageClass": platform.on_prem.blob_storage_class_name,
                "size": platform.on_prem.blob_storage_size,
            },
            "accessKey": platform.on_prem.blob_storage_access_key,
            "secretKey": platform.on_prem.blob_storage_secret_key,
            "ingress": {
                "enabled": True,
                "annotations": {
                    "kubernetes.io/ingress.class": "traefik",
                    "traefik.frontend.rule.type": "PathPrefix",
                },
                "hosts": [platform.on_prem.blob_storage_public_url.host],
            },
            "environment": {"MINIO_REGION_NAME": platform.on_prem.blob_storage_region},
        }

    def create_consul_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result = {
            "Image": f"{platform.docker_registry.url.host}/consul",
            "StorageClass": platform.standard_storage_class_name,
            "Replicas": 3,
        }
        if platform.on_prem:
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
            "image": f"{platform.docker_registry.url.host}/traefik",
            "imageTag": "1.7.20-alpine",
            "imagePullSecrets": platform.image_pull_secret_names,
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
        }
        if platform.gcp:
            result["timeouts"] = {
                "responding": {
                    # must be greater than lb timeout
                    # gcp lb default timeout is 600s and cannot be changed
                    "idleTimeout": "660s"  # must be greater than lb timeout
                }
            }
        if platform.aws:
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
        if platform.azure:
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
        if platform.on_prem:
            result["replicas"] = 1
            result["serviceType"] = "NodePort"
            result["service"] = {
                "nodePorts": {
                    "http": platform.on_prem.http_node_port,
                    "https": platform.on_prem.https_node_port,
                }
            }
            result["deployment"]["hostPort"] = {
                "httpEnabled": True,
                "httpsEnabled": True,
            }
            result["timeouts"] = {"responding": {"idleTimeout": "600s"}}
        return result

    def create_cluster_autoscaler_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        assert platform.aws
        if platform.kubernetes_version.startswith("1.14"):
            image_tag = "v1.14.8"
        elif platform.kubernetes_version.startswith("1.15"):
            image_tag = "v1.15.7"
        elif platform.kubernetes_version.startswith("1.16"):
            image_tag = "v1.16.6"
        elif platform.kubernetes_version.startswith("1.17"):
            image_tag = "v1.17.4"
        elif platform.kubernetes_version.startswith("1.18"):
            image_tag = "v1.18.3"
        elif platform.kubernetes_version.startswith("1.19"):
            image_tag = "v1.19.1"
        elif platform.kubernetes_version.startswith("1.20"):
            image_tag = "v1.20.0"
        else:
            raise ValueError(
                f"Cluster autoscaler for Kubernetes {platform.kubernetes_version} "
                "is not supported"
            )
        docker_server = platform.docker_registry.url.host
        result = {
            "cloudProvider": "aws",
            "awsRegion": platform.aws.region,
            "image": {
                "repository": f"{docker_server}/autoscaling/cluster-autoscaler",
                "tag": image_tag,
                "pullSecrets": platform.image_pull_secret_names,
            },
            "rbac": {"create": True},
            "autoDiscovery": {"clusterName": platform.cluster_name},
            "extraArgs": {
                # least-waste will expand the ASG that will waste
                # the least amount of CPU/MEM resources
                "expander": "least-waste",
                # If true cluster autoscaler will never delete nodes with pods
                # with local storage, e.g. EmptyDir or HostPath
                "skip-nodes-with-local-storage": False,
                # If true cluster autoscaler will never delete nodes with pods
                # from kube-system (except for DaemonSet or mirror pods)
                "skip-nodes-with-system-pods": False,
                # Detect similar node groups and balance the number of nodes
                # between them. This option is required for balancing nodepool
                # nodes between multiple availability zones.
                "balance-similar-node-groups": True,
            },
        }
        if platform.aws.role_arn:
            result["podAnnotations"] = {"iam.amazonaws.com/role": platform.aws.role_arn}
        return result

    def create_adjust_inotify_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        return {"image": {"repository": f"{platform.docker_registry.url.host}/busybox"}}

    def create_nvidia_gpu_driver_gcp_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        return {
            "kubectlImage": {"repository": f"{docker_server}/bitnami/kubectl"},
            "pauseImage": {"repository": f"{docker_server}/google_containers/pause"},
            "gpuNodeLabel": platform.kubernetes_node_labels.accelerator,
        }

    def create_nvidia_gpu_driver_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        return {
            "image": {"repository": f"{docker_server}/nvidia/k8s-device-plugin"},
            "gpuNodeLabel": platform.kubernetes_node_labels.accelerator,
        }

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
        docker_server = platform.docker_registry.url.host
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
        docker_server = platform.docker_registry.url.host
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
        if platform.gcp:
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
                "project": platform.gcp.project,
                "maxCatalogEntries": 10000,
            }
            result["secrets"].append(
                {
                    "name": gcp_key_secret_name,
                    "data": {
                        "username": "_json_key",
                        "password": platform.gcp.service_account_key,
                    },
                }
            )
        if platform.aws:
            result["AWS_DEFAULT_REGION"] = platform.aws.region
            result["upstreamRegistry"] = {
                "type": "aws_ecr",
                "url": str(platform.aws.registry_url),
                "project": "neuro",
                "maxCatalogEntries": 1000,
            }
            if platform.aws.role_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
        if platform.azure:
            azure_credentials_secret_name = (
                f"{self._release_names.platform}-registry-azure-credentials"
            )
            result["upstreamRegistry"] = {
                "type": "oauth",
                "url": str(platform.azure.registry_url),
                "tokenUrl": str(platform.azure.registry_url / "oauth2/token"),
                "tokenService": platform.azure.registry_url.host,
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
                        "username": platform.azure.registry_username,
                        "password": platform.azure.registry_password,
                    },
                }
            )
        if platform.on_prem:
            docker_registry_credentials_secret_name = (
                f"{self._release_names.platform}-docker-registry"
            )
            result["upstreamRegistry"] = {
                "type": "basic",
                "url": str(platform.on_prem.registry_url),
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
                        "username": platform.on_prem.registry_username,
                        "password": platform.on_prem.registry_password,
                    },
                }
            )
        return result

    def create_platform_monitoring_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
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
                "job": platform.kubernetes_node_labels.job,
                "nodePool": platform.kubernetes_node_labels.node_pool,
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
        if platform.gcp:
            result["logs"] = {
                "persistence": {
                    "type": "gcp",
                    "gcp": {
                        "serviceAccountKeyBase64": (
                            platform.gcp.service_account_key_base64
                        ),
                        "project": platform.gcp.project,
                        "region": platform.gcp.region,
                        "bucket": platform.monitoring_logs_bucket_name,
                    },
                }
            }
        if platform.aws:
            if platform.aws.role_arn:
                result["podAnnotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
                result["fluentd"]["podAnnotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
            result["logs"] = {
                "persistence": {
                    "type": "aws",
                    "aws": {
                        "region": platform.aws.region,
                        "bucket": platform.monitoring_logs_bucket_name,
                    },
                }
            }
        if platform.azure:
            result["logs"] = {
                "persistence": {
                    "type": "azure",
                    "azure": {
                        "storageAccountName": platform.azure.blob_storage_account_name,
                        "storageAccountKey": platform.azure.blob_storage_account_key,
                        "region": platform.azure.region,
                        "bucket": platform.monitoring_logs_bucket_name,
                    },
                }
            }
        if platform.on_prem:
            result["logs"] = {
                "persistence": {
                    "type": "minio",
                    "minio": {
                        "url": str(platform.on_prem.blob_storage_url),
                        "accessKey": platform.on_prem.blob_storage_access_key,
                        "secretKey": platform.on_prem.blob_storage_secret_key,
                        "region": platform.on_prem.blob_storage_region,
                        "bucket": platform.monitoring_logs_bucket_name,
                    },
                }
            }
            result["NP_MONITORING_K8S_KUBELET_PORT"] = platform.on_prem.kubelet_port
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
                                        "key": platform.kubernetes_node_labels.job,
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
        docker_server = platform.docker_registry.url.host
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
                platform.kubernetes_node_labels.job,
                LabelsConfig.job,
            ),
            self._relabel_reports_label(
                platform.kubernetes_node_labels.node_pool,
                LabelsConfig.node_pool,
            ),
            self._relabel_reports_label(
                platform.kubernetes_node_labels.accelerator,
                LabelsConfig.accelerator,
            ),
            self._relabel_reports_label(
                platform.kubernetes_node_labels.preemptible,
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
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platform-reports"},
            "nvidiaDCGMExporterImage": {
                "repository": f"{docker_server}/nvidia/dcgm-exporter"
            },
            "nodePoolLabels": {
                "job": platform.kubernetes_node_labels.job,
                "gpu": platform.kubernetes_node_labels.accelerator,
                "nodePool": platform.kubernetes_node_labels.node_pool,
                "preemptible": platform.kubernetes_node_labels.preemptible,
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
        if platform.gcp:
            result["thanos"]["objstore"] = {
                "type": "GCS",
                "config": {
                    "bucket": platform.monitoring_metrics_bucket_name,
                    "service_account": b64decode(
                        platform.gcp.service_account_key_base64
                    ).decode(),
                },
            }
            result["cloudProvider"] = {
                "type": "gcp",
                "region": platform.gcp.region,
                "serviceAccountSecret": {
                    "name": f"{self._release_names.platform}-reports-gcp-key",
                    "key": "key.json",
                },
            }
            result["secrets"].append(
                {
                    "name": f"{self._release_names.platform}-reports-gcp-key",
                    "data": {"key.json": platform.gcp.service_account_key},
                }
            )
        if platform.aws:
            if platform.aws.role_arn:
                result["metricsServer"] = {
                    "podMetadata": {
                        "annotations": {"iam.amazonaws.com/role": platform.aws.role_arn}
                    }
                }
                prometheus_spec["podMetadata"] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws.role_arn}
                }
                result["thanos"]["store"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
                result["thanos"]["bucket"] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws.role_arn}
                }
                result["thanos"]["compact"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring_metrics_bucket_name,
                    "endpoint": f"s3.{platform.aws.region}.amazonaws.com",
                },
            }
            result["cloudProvider"] = {"type": "aws", "region": platform.aws.region}
        if platform.azure:
            result["thanos"]["objstore"] = {
                "type": "AZURE",
                "config": {
                    "container": platform.monitoring_metrics_bucket_name,
                    "storage_account": platform.azure.blob_storage_account_name,
                    "storage_account_key": platform.azure.blob_storage_account_key,
                },
            }
            result["cloudProvider"] = {"type": "azure", "region": platform.azure.region}
        if platform.on_prem:
            result["objectStore"] = {"supported": False}
            result["prometheusProxy"] = {
                "prometheus": {"host": "prometheus-prometheus", "port": 9090}
            }
            prometheus_spec["retention"] = (
                platform.monitoring_metrics_retention_time or "15d"
            )  # 15d is default prometheus retention time
            if platform.monitoring_metrics_storage_size:
                prometheus_spec["retentionSize"] = (
                    platform.monitoring_metrics_storage_size.replace("i", "")
                    + "B"  # Gi -> GB
                )
            prometheus_spec["storageSpec"]["volumeClaimTemplate"]["spec"] = {
                "storageClassName": platform.monitoring_metrics_storage_class_name,
                "resources": {
                    "requests": {"storage": platform.monitoring_metrics_storage_size}
                },
            }
            # Because of the bug in helm the only way to delete thanos values
            # is to set it to empty string
            prometheus_spec["thanos"] = ""
            del result["thanos"]
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
        docker_server = platform.docker_registry.url.host
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
        docker_server = platform.docker_registry.url.host
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
                "job": platform.kubernetes_node_labels.job,
                "gpu": platform.kubernetes_node_labels.accelerator,
                "preemptible": platform.kubernetes_node_labels.preemptible,
                "nodePool": platform.kubernetes_node_labels.node_pool,
            },
            "storages": [
                {
                    "path": s.path,
                    "type": "pvc",
                    "claimName": platform.get_storage_claim_name(s.path),
                }
                for i, s in enumerate(platform.storages)
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
        if platform.azure:
            result["jobs"][
                "preemptibleTolerationKey"
            ] = "kubernetes.azure.com/scalesetpriority"
        if platform.docker_hub_registry:
            result["jobs"]["imagePullSecret"] = platform.docker_hub_config_secret_name
        return result

    def create_platform_buckets_api_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platformbucketsapi"},
            "NP_BUCKETS_API_K8S_NS": platform.jobs_namespace,
            "authUrl": str(platform.auth_url),
            "platform": {
                "clusterName": platform.cluster_name,
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
            "corsOrigins": ",".join(platform.ingress_cors_origins),
            "disableCreation": platform.buckets_disable_creation,
        }
        result.update(**self._create_tracing_values(platform))
        if platform.aws:
            result["bucketProvider"] = {
                "type": "aws",
                "aws": {
                    "regionName": platform.aws.region,
                    "s3RoleArn": platform.aws.s3_role_arn,
                },
            }
            if platform.aws.role_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
        elif platform.emc_ecs_credentials:
            secret_name = f"{self._release_names.platform}-buckets-emc-ecs-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {
                        "key": platform.emc_ecs_credentials.access_key_id,
                        "secret": platform.emc_ecs_credentials.secret_access_key,
                    },
                }
            )
            result["bucketProvider"] = {
                "type": "emc_ecs",
                "emc_ecs": {
                    "s3RoleUrn": platform.emc_ecs_credentials.s3_assumable_role,
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
                    "s3EndpointUrl": str(platform.emc_ecs_credentials.s3_endpoint),
                    "managementEndpointUrl": str(
                        platform.emc_ecs_credentials.management_endpoint
                    ),
                },
            }
        elif platform.open_stack_credentials:
            secret_name = f"{self._release_names.platform}-buckets-open-stack-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {
                        "accountId": platform.open_stack_credentials.account_id,
                        "password": platform.open_stack_credentials.password,
                    },
                }
            )
            result["bucketProvider"] = {
                "type": "open_stack",
                "open_stack": {
                    "regionName": platform.open_stack_credentials.region_name,
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
                    "s3EndpointUrl": str(platform.open_stack_credentials.s3_endpoint),
                    "endpointUrl": str(platform.open_stack_credentials.endpoint),
                },
            }
        elif platform.on_prem:
            result["bucketProvider"] = {
                "type": "minio",
                "minio": {
                    "url": str(platform.on_prem.blob_storage_url),
                    "publicUrl": str(platform.on_prem.blob_storage_public_url),
                    "accessKeyId": platform.on_prem.blob_storage_access_key,
                    "secretAccessKey": platform.on_prem.blob_storage_secret_key,
                    "regionName": platform.on_prem.blob_storage_region,
                },
            }
        elif platform.azure:
            secret_name = (
                f"{self._release_names.platform}-buckets-azure-storage-account-key"
            )
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {"key": platform.azure.blob_storage_account_key},
                }
            )
            result["bucketProvider"] = {
                "type": "azure",
                "azure": {
                    "url": (
                        f"https://{platform.azure.blob_storage_account_name}"
                        f".blob.core.windows.net"
                    ),
                    "credential": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": "token",
                            }
                        }
                    },
                },
            }
        elif platform.gcp:
            secret_name = f"{self._release_names.platform}-buckets-gcp-sa-key"
            result["secrets"].append(
                {
                    "name": secret_name,
                    "data": {"SAKeyB64": platform.gcp.service_account_key_base64},
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
