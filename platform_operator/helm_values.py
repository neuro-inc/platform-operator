import secrets
import string
from base64 import b64decode
from typing import Any, Dict, Optional

from .models import HelmChartNames, HelmReleaseNames, LabelsConfig, PlatformConfig


class HelmValuesFactory:
    def __init__(
        self, helm_release_names: HelmReleaseNames, helm_chart_names: HelmChartNames
    ) -> None:
        self._release_names = helm_release_names
        self._chart_names = helm_chart_names

    def create_platform_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "tags": {platform.cloud_provider: True},
            "dockerImage": {"repository": f"{docker_server}/docker"},
            "alpineImage": {"repository": f"{docker_server}/alpine"},
            "pauseImage": {"repository": f"{docker_server}/google_containers/pause"},
            "serviceToken": platform.token,
            "kubernetes": {
                "nodePools": platform.jobs_node_pools,
                "labels": {"nodePool": platform.kubernetes_node_labels.node_pool},
                # NOTE: should images prepulling be configured in config service?
                "imagesPrepull": {
                    "refreshInterval": "1h",
                    "images": [
                        {"image": "neuromation/base"},
                        {"image": "neuromation/web-shell"},
                    ],
                },
            },
            "standardStorageClass": {
                "create": not platform.on_prem,
                "name": platform.standard_storage_class_name,
            },
            "ingress": {
                "host": platform.ingress_url.host,
                "jobFallbackHost": str(platform.jobs_fallback_host),
                "registryHost": platform.ingress_registry_url.host,
            },
            "ingressController": {"enabled": platform.ingress_controller_enabled},
            "jobs": {
                "namespace": {
                    "create": platform.jobs_namespace_create,
                    "name": platform.jobs_namespace,
                },
                "label": platform.kubernetes_node_labels.job,
            },
            self._chart_names.adjust_inotify: self.create_adjust_inotify_values(
                platform
            ),
            self._chart_names.consul: self.create_consul_values(platform),
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
            self._chart_names.platform_secrets: (
                self.create_platform_secrets_values(platform)
            ),
            self._chart_names.platform_reports: (
                self.create_platform_reports_values(platform)
            ),
            self._chart_names.platform_disk_api: (
                self.create_platform_disk_api_values(platform)
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
        if not platform.on_prem:
            result[
                self._chart_names.platform_object_storage
            ] = self.create_platform_object_storage_values(platform)
        if platform.gcp:
            result[
                self._chart_names.nvidia_gpu_driver_gcp
            ] = self.create_nvidia_gpu_driver_gcp_values(platform)
            if platform.gcp.storage_type == "nfs":
                result["storage"] = {
                    "nfs": {
                        "server": platform.gcp.storage_nfs_server,
                        "path": platform.gcp.storage_nfs_path,
                    }
                }
            if platform.gcp.storage_type == "gcs":
                result["storage"] = {
                    "gcs": {"bucketName": platform.gcp.storage_gcs_bucket_name}
                }
        else:
            result[
                self._chart_names.nvidia_gpu_driver
            ] = self.create_nvidia_gpu_driver_values(platform)
        if platform.aws:
            result["storage"] = {
                "nfs": {
                    "server": platform.aws.storage_nfs_server,
                    "path": platform.aws.storage_nfs_path,
                }
            }
            result[
                self._chart_names.cluster_autoscaler
            ] = self.create_cluster_autoscaler_values(platform)
        if platform.azure:
            result["storage"] = {
                "azureFile": {
                    "storageAccountName": platform.azure.storage_account_name,
                    "storageAccountKey": platform.azure.storage_account_key,
                    "shareName": platform.azure.storage_share_name,
                }
            }
            result["blobStorage"] = {
                "azure": {
                    "storageAccountName": platform.azure.blob_storage_account_name,
                    "storageAccountKey": platform.azure.blob_storage_account_key,
                }
            }
        if platform.on_prem:
            result["storage"] = {
                "nfs": {
                    "server": (
                        f"{self._release_names.nfs_server}"
                        f".{platform.namespace}.svc.cluster.local"
                    ),
                    "path": "/",
                }
            }
            result[
                self._chart_names.docker_registry
            ] = self.create_docker_registry_values(platform)
            result[self._chart_names.minio] = self.create_minio_values(platform)
        return result

    def create_obs_csi_driver_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.gcp
        return {
            "image": f"{platform.docker_registry.url.host}/obs-csi-driver",
            "driverName": "obs.csi.neu.ro",
            "credentialsSecret": {
                "create": True,
                "gcpServiceAccountKeyBase64": platform.gcp.service_account_key_base64,
            },
        }

    def create_nfs_server_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        return {
            "image": {"repository": f"{platform.docker_registry.url.host}/volume-nfs"},
            "imagePullSecrets": [
                {"name": name} for name in platform.image_pull_secret_names
            ],
            "rbac": {"create": True},
            "persistence": {
                "enabled": True,
                "storageClass": platform.on_prem.storage_class_name,
                "size": platform.on_prem.storage_size,
            },
        }

    def create_docker_registry_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        docker_registry = platform.docker_registry
        return {
            "image": {"repository": f"{docker_registry.url.host}/registry"},
            "ingress": {"enabled": False},
            "persistence": {
                "enabled": True,
                "storageClass": platform.on_prem.registry_storage_class_name,
                "size": platform.on_prem.registry_storage_size,
            },
            "secrets": {
                "haSharedSecret": (
                    f"{docker_registry.username}:{docker_registry.password}"
                )
            },
        }

    def create_minio_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        return {
            "image": {
                "repository": f"{platform.docker_registry.url.host}/minio/minio",
                "tag": "RELEASE.2020-03-05T01-04-19Z",
            },
            "imagePullSecrets": [
                {"name": name} for name in platform.image_pull_secret_names
            ],
            "mode": "standalone",
            "persistence": {
                "enabled": True,
                "storageClass": platform.on_prem.blob_storage_class_name,
                "size": platform.on_prem.blob_storage_size,
            },
            "accessKey": platform.on_prem.blob_storage_access_key,
            "secretKey": platform.on_prem.blob_storage_secret_key,
            "environment": {"MINIO_REGION_NAME": platform.on_prem.blob_storage_region},
        }

    def create_consul_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result = {
            "Image": f"{platform.docker_registry.url.host}/consul",
            "StorageClass": platform.standard_storage_class_name,
            "Replicas": 3,
        }
        if platform.on_prem:
            result["Replicas"] = platform.on_prem.masters_count
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
                    "endpoint": f"{self._release_names.platform}-consul:8500",
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
            result["replicas"] = platform.on_prem.masters_count
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

    def create_platform_storage_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        return {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_STORAGE_AUTH_URL": str(platform.auth_url),
            "NP_STORAGE_PVC_CLAIM_NAME": f"{self._release_names.platform}-storage",
            "NP_CORS_ORIGINS": self._create_cors_origins(platform.cluster_name),
            "image": {"repository": f"{docker_server}/platformstorageapi"},
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-storage-token",
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-storage-token",
                    "data": {"token": platform.token},
                }
            ],
        }

    def create_platform_object_storage_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "image": {"repository": f"{docker_server}/platformobjectstorage"},
            "minio": {"image": {"repository": f"{docker_server}/minio/minio"}},
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_OBSTORAGE_AUTH_URL": str(platform.auth_url),
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": (
                                f"{self._release_names.platform}-object-storage-token"
                            ),
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-object-storage-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        if platform.gcp:
            result["objectStorage"] = {
                "provider": "gcp",
                "location": platform.gcp.region,
                "gcp": {
                    "project": platform.gcp.project,
                    "keySecret": {
                        "name": f"{self._release_names.platform}-object-storage-gcp-key"
                    },
                },
            }
            result["secrets"].append(
                {
                    "name": f"{self._release_names.platform}-object-storage-gcp-key",
                    "data": {"key.json": platform.gcp.service_account_key},
                }
            )
        if platform.aws:
            result["objectStorage"] = {
                "provider": "aws",
                "location": platform.aws.region,
                "aws": {
                    "accessKey": {"value": ""},
                    "secretKey": {"value": ""},
                },
            }
            if platform.aws.role_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_arn
                }
        if platform.azure:
            azure_object_storage_secret_name = (
                f"{self._release_names.platform}-object-storage-azure-credentials"
            )
            result["objectStorage"] = {
                "provider": "azure",
                "location": platform.azure.region,
                "azure": {
                    "accountName": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": azure_object_storage_secret_name,
                                "key": "account_name",
                            }
                        }
                    },
                    "accountKey": {
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": azure_object_storage_secret_name,
                                "key": "account_key",
                            }
                        }
                    },
                },
            }
            result["secrets"].append(
                {
                    "name": azure_object_storage_secret_name,
                    "data": {
                        "account_name": platform.azure.blob_storage_account_name,
                        "account_key": platform.azure.blob_storage_account_key,
                    },
                }
            )
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
                "url": f"http://{self._release_names.platform}-docker-registry:5000",
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
                        "username": platform.docker_registry.username,
                        "password": platform.docker_registry.password,
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
            "NP_CORS_ORIGINS": self._create_cors_origins(platform.cluster_name),
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
            "dockerEngine": {"image": {"repository": f"{docker_server}/nginx"}},
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
                        "url": f"http://{self._release_names.platform}-minio:9000",
                        "accessKey": platform.on_prem.blob_storage_access_key,
                        "secretKey": platform.on_prem.blob_storage_secret_key,
                        "region": platform.on_prem.blob_storage_region,
                        "bucket": platform.monitoring_logs_bucket_name,
                    },
                }
            }
            result["NP_MONITORING_K8S_KUBELET_PORT"] = platform.on_prem.kubelet_port
        return result

    def create_platform_secrets_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        docker_server = platform.docker_registry.url.host
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_SECRETS_K8S_NS": platform.jobs_namespace,
            "NP_SECRETS_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_CORS_ORIGINS": self._create_cors_origins(platform.cluster_name),
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
        return result

    def create_platform_reports_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        alphabet = string.ascii_letters + string.digits
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
                        "repository": f"{docker_server}/grafana/grafana",
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "sidecar": {
                    "image": {
                        "repository": f"{docker_server}/kiwigrid/k8s-sidecar",
                        "pullSecrets": platform.image_pull_secret_names,
                    }
                },
                "adminPassword": "".join(secrets.choice(alphabet) for i in range(16)),
            },
        }
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
            prometheus_spec["storageSpec"]["volumeClaimTemplate"]["spec"] = {
                "storageClassName": platform.monitoring_metrics_storage_class_name,
                "resources": {
                    "requests": {"storage": platform.monitoring_metrics_storage_size}
                },
            }
            prometheus_spec["thanos"] = {}
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
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_DISK_API_K8S_NS": platform.jobs_namespace,
            "NP_DISK_API_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_DISK_API_STORAGE_LIMIT_PER_USER": str(
                platform.disks_storage_limit_per_user_gb * 1024 ** 3
            ),
            "NP_CORS_ORIGINS": self._create_cors_origins(platform.cluster_name),
            "image": {"repository": f"{docker_server}/platformdiskapi"},
            "platform": {
                "token": {
                    "valueFrom": {
                        "secretKeyRef": {
                            "name": f"{self._release_names.platform}-disks-token",
                            "key": "token",
                        }
                    }
                }
            },
            "ingress": {"enabled": True, "hosts": [platform.ingress_url.host]},
            "secrets": [
                {
                    "name": f"{self._release_names.platform}-disks-token",
                    "data": {"token": platform.token},
                }
            ],
        }
        if platform.aws:
            result["NP_DISK_PROVIDER"] = "aws"
        if platform.azure:
            result["NP_DISK_PROVIDER"] = "azure"
        if platform.gcp:
            result["NP_DISK_PROVIDER"] = "gcp"
        return result

    def _create_cors_origins(self, cluster_name: str) -> str:
        # TODO: get cors configuration from config service
        if cluster_name in ("megafon-poc"):
            cors_origins = [
                "https://megafon-release.neu.ro",
                "http://megafon-neuro.netlify.app",
                "https://release--neuro-web.netlify.app",
                "https://app.neu.ro",
                "https://app.ml.megafon.ru",
            ]
            if cluster_name == "megafon-poc":
                cors_origins.append("https://master--megafon-neuro.netlify.app")
            return ",".join(cors_origins)
        return "https://release--neuro-web.netlify.app,https://app.neu.ro"
