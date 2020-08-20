import secrets
import string
from base64 import b64decode
from typing import Any, Dict

from .models import HelmChartNames, HelmReleaseNames, PlatformConfig


class HelmValuesFactory:
    def __init__(
        self, helm_release_names: HelmReleaseNames, helm_chart_names: HelmChartNames
    ) -> None:
        self._release_names = helm_release_names
        self._chart_names = helm_chart_names

    def create_platform_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "tags": {platform.cloud_provider: True},
            "serviceToken": platform.token,
            "kubernetes": {
                "nodePools": platform.jobs_node_pools,
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
            "imagePullSecret": {
                "create": True,
                "name": platform.image_pull_secret_name,
                "credentials": {
                    "url": str(platform.docker_registry.url),
                    "email": platform.docker_registry.email,
                    "username": platform.docker_registry.username,
                    "password": platform.docker_registry.password,
                },
            },
            "ingress": {
                "host": platform.ingress_url.host,
                "jobFallbackHost": str(platform.jobs_fallback_host),
                "registryHost": platform.ingress_registry_url.host,
            },
            "jobs": {
                "namespace": {"create": True, "name": platform.jobs_namespace},
                "label": platform.jobs_label,
            },
            self._chart_names.consul: self.create_consul_values(platform),
            self._chart_names.traefik: self.create_traefik_values(platform),
            self._chart_names.platform_storage: self.create_platform_storage_values(
                platform
            ),
            self._chart_names.platform_registry: self.create_platform_registry_values(
                platform
            ),
            self._chart_names.platform_ssh_auth: self.create_platform_ssh_auth_values(
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
        }
        if not platform.on_prem:
            result[
                self._chart_names.platform_object_storage
            ] = self.create_platform_object_storage_values(platform)
        if platform.gcp:
            result["gcp"] = {
                "serviceAccountKeyBase64": platform.gcp.service_account_key_base64
            }
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
            result["registry"] = {
                "username": platform.azure.registry_username,
                "password": platform.azure.registry_password,
            }
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
            result["registry"] = {
                "username": platform.docker_registry.username,
                "password": platform.docker_registry.password,
            }
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

    def create_nfs_server_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        assert platform.on_prem
        return {
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
            "StorageClass": platform.standard_storage_class_name,
            "Replicas": 3,
        }
        if platform.on_prem:
            result["Replicas"] = platform.on_prem.masters_count
        return result

    def create_traefik_values(self, platform: PlatformConfig) -> Dict[str, Any]:
        result: Dict[str, Any] = {
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
                "staging": platform.ingress_acme_environment == "staging",
                "persistence": {"enabled": False},
                "keyType": "RSA4096",
                "challengeType": "dns-01",
                "dnsProvider": {
                    "name": "exec",
                    "exec": {"EXEC_PATH": "/dns-01/resolve_dns_challenge.sh"},
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
                {
                    "name": "resolve-dns-challenge-script",
                    "configMap": {
                        "name": (
                            f"{self._release_names.platform}"
                            "-resolve-dns-challenge-script"
                        ),
                        "defaultMode": 0o777,
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
                {"name": "NP_PLATFORM_API_URL", "value": str(platform.api_url)},
                {"name": "NP_CLUSTER_NAME", "value": platform.cluster_name},
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
        if platform.aws:
            result["service"] = {
                "annotations": {
                    (
                        "service.beta.kubernetes.io/"
                        "aws-load-balancer-connection-idle-timeout"
                    ): "3600"
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
            result["deploymentStrategy"] = {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0},
            }
        return result

    def create_cluster_autoscaler_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        assert platform.aws
        result = {
            "cloudProvider": "aws",
            "awsRegion": platform.aws.region,
            "image": {"tag": "v1.13.9"},
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
        if platform.aws.role_auto_scaling_arn:
            result["podAnnotations"] = {
                "iam.amazonaws.com/role": platform.aws.role_auto_scaling_arn
            }
        return result

    def create_platform_storage_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        return {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_STORAGE_AUTH_URL": str(platform.auth_url),
            "NP_STORAGE_PVC_CLAIM_NAME": (f"{self._release_names.platform}-storage"),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
        }

    def create_platform_object_storage_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_OBSTORAGE_PROVIDER": platform.cloud_provider,
            "NP_OBSTORAGE_AUTH_URL": str(platform.auth_url),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
        }
        secret_name = f"{self._release_names.platform}-blob-storage-key"
        if platform.gcp:
            result["NP_OBSTORAGE_LOCATION"] = platform.gcp.region
            result["NP_OBSTORAGE_GCP_PROJECT_ID"] = platform.gcp.project
            result["NP_OBSTORAGE_GCP_KEY_SECRET"] = secret_name
        if platform.aws:
            result["NP_OBSTORAGE_LOCATION"] = platform.aws.region
            result["NP_OBSTORAGE_AWS_SECRET"] = secret_name
            if platform.aws.role_s3_arn:
                result["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_s3_arn
                }
        if platform.azure:
            result["NP_OBSTORAGE_LOCATION"] = platform.azure.region
            result["NP_OBSTORAGE_AZURE_SECRET"] = secret_name
        return result

    def create_platform_registry_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "INGRESS_HOST": platform.ingress_registry_url.host,
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_REGISTRY_AUTH_URL": str(platform.auth_url),
            "NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES": 10000,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
        }
        if platform.gcp:
            result["NP_REGISTRY_UPSTREAM_TYPE"] = "oauth"
            result["NP_REGISTRY_UPSTREAM_URL"] = "https://gcr.io"
            result["NP_REGISTRY_UPSTREAM_PROJECT"] = platform.gcp.project
        if platform.aws:
            result["NP_REGISTRY_UPSTREAM_TYPE"] = "aws_ecr"
            result["NP_REGISTRY_UPSTREAM_URL"] = str(platform.aws.registry_url)
            result["NP_REGISTRY_UPSTREAM_PROJECT"] = "neuro"
            result["NP_REGISTRY_UPSTREAM_MAX_CATALOG_ENTRIES"] = 1000
            result["AWS_DEFAULT_REGION"] = platform.aws.region
        if platform.azure:
            result["NP_REGISTRY_UPSTREAM_TYPE"] = "oauth"
            result["NP_REGISTRY_UPSTREAM_URL"] = str(platform.azure.registry_url)
            result["NP_REGISTRY_UPSTREAM_PROJECT"] = "neuro"
            result[
                "NP_REGISTRY_UPSTREAM_TOKEN_SERVICE"
            ] = platform.azure.registry_url.host
            result["NP_REGISTRY_UPSTREAM_TOKEN_URL"] = str(
                platform.azure.registry_url / "oauth2/token"
            )
        if platform.aws and platform.aws.role_ecr_arn:
            result["annotations"] = {
                "iam.amazonaws.com/role": platform.aws.role_ecr_arn
            }
        if platform.on_prem:
            result["NP_REGISTRY_UPSTREAM_TYPE"] = "basic"
            result[
                "NP_REGISTRY_UPSTREAM_URL"
            ] = f"http://{self._release_names.platform}-docker-registry:5000"
            result["NP_REGISTRY_UPSTREAM_PROJECT"] = "neuro"
        return result

    def create_platform_monitoring_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "NP_MONITORING_CLUSTER_NAME": platform.cluster_name,
            "NP_MONITORING_K8S_NS": platform.jobs_namespace,
            "NP_MONITORING_PLATFORM_API_URL": str(platform.api_url),
            "NP_MONITORING_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_MONITORING_PLATFORM_CONFIG_URL": str(platform.api_url),
            "NP_MONITORING_REGISTRY_URL": str(platform.ingress_registry_url),
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
            "fluentd": {
                "persistence": {
                    "enabled": True,
                    "storageClassName": platform.standard_storage_class_name,
                }
            },
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
            if platform.aws.role_s3_arn:
                result["monitoring"] = {
                    "podAnnotations": {
                        "iam.amazonaws.com/role": platform.aws.role_s3_arn
                    }
                }
                result["fluentd"]["podAnnotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_s3_arn
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

        # TODO: get cors configuration from config service
        if platform.cluster_name in ("megafon-poc", "megafon-public"):
            result["NP_CORS_ORIGINS"] = (
                "https://megafon-release.neu.ro"
                ",http://megafon-neuro.netlify.app"
                ",https://release--neuro-web.netlify.app"
                ",https://app.neu.ro"
                ",https://app.ml.megafon.ru"
            )
        if platform.cluster_name == "megafon-poc":
            result["NP_CORS_ORIGINS"] += ",https://master--megafon-neuro.netlify.app"
        return result

    def create_platform_ssh_auth_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "NP_AUTH_URL": str(platform.auth_url),
            "NP_PLATFORM_API_URL": str(platform.api_url),
            "NP_K8S_NS": platform.jobs_namespace,
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
        }
        if platform.aws:
            result["service"] = {
                "annotations": {
                    (
                        "service.beta.kubernetes.io/"
                        "aws-load-balancer-connection-idle-timeout"
                    ): "3600"
                }
            }
        if platform.on_prem:
            result["NODEPORT"] = platform.on_prem.ssh_auth_node_port
        return result

    def create_platform_secrets_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_SECRETS_K8S_NS": platform.jobs_namespace,
            "NP_SECRETS_PLATFORM_AUTH_URL": str(platform.auth_url),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
            "NP_CORS_ORIGINS": (
                "https://release--neuro-web.netlify.app,https://app.neu.ro"
            ),
        }
        # TODO: get cors configuration from config service
        if platform.cluster_name in ("megafon-poc", "megafon-public"):
            result["NP_CORS_ORIGINS"] = (
                "https://megafon-release.neu.ro"
                ",http://megafon-neuro.netlify.app"
                ",https://release--neuro-web.netlify.app"
                ",https://app.neu.ro"
                ",https://app.ml.megafon.ru"
            )
        if platform.cluster_name == "megafon-poc":
            result["NP_CORS_ORIGINS"] += ",https://master--megafon-neuro.netlify.app"
        return result

    def create_platform_reports_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        alphabet = string.ascii_letters + string.digits
        result: Dict[str, Any] = {
            "image": {"pullSecretName": platform.image_pull_secret_name},
            "platform": {
                "clusterName": platform.cluster_name,
                "authUrl": str(platform.auth_url),
                "apiUrl": str(platform.api_url),
            },
            "grafanaProxy": {"ingress": {"host": platform.ingress_metrics_url.host}},
            "prometheus-operator": {
                "prometheus": {
                    "prometheusSpec": {
                        "storageSpec": {
                            "volumeClaimTemplate": {
                                "spec": {
                                    "storageClassName": (
                                        platform.standard_storage_class_name
                                    )
                                },
                            }
                        }
                    }
                },
                "prometheusOperator": {
                    "kubeletService": {"namespace": platform.namespace}
                },
                "kubelet": {"namespace": platform.namespace},
                "grafana": {
                    "adminPassword": "".join(
                        secrets.choice(alphabet) for i in range(16)
                    )
                },
            },
            "thanos": {
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
        }
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
        if platform.aws:
            if platform.aws.role_s3_arn:
                result["prometheus-operator"]["prometheus"]["prometheusSpec"][
                    "podMetadata"
                ] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws.role_s3_arn}
                }
                result["thanos"]["store"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_s3_arn
                }
                result["thanos"]["bucket"] = {
                    "annotations": {"iam.amazonaws.com/role": platform.aws.role_s3_arn}
                }
                result["thanos"]["compact"]["annotations"] = {
                    "iam.amazonaws.com/role": platform.aws.role_s3_arn
                }
            result["thanos"]["objstore"] = {
                "type": "S3",
                "config": {
                    "bucket": platform.monitoring_metrics_bucket_name,
                    "endpoint": f"s3.{platform.aws.region}.amazonaws.com",
                },
            }
        if platform.azure:
            result["thanos"]["objstore"] = {
                "type": "AZURE",
                "config": {
                    "container": platform.monitoring_metrics_bucket_name,
                    "storage_account": platform.azure.blob_storage_account_name,
                    "storage_account_key": platform.azure.blob_storage_account_key,
                },
            }
        if platform.on_prem:
            result["objectStoreSupported"] = False
            result["prometheusProxy"] = {
                "prometheus": {"host": "prometheus-prometheus", "port": 9090}
            }
            del result["thanos"]
        return result
