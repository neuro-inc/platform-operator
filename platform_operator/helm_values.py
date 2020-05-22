from typing import Any, Dict

from .models import PlatformConfig


class HelmValuesFactory:
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
                    "endpoint": f"{platform.namespace}-consul:8500",
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
                        "name": (f"{platform.namespace}-resolve-dns-challenge-script"),
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
            "NP_STORAGE_PVC_CLAIM_NAME": (f"{platform.namespace}-storage"),
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
        secret_name = f"{platform.namespace}-blob-storage-key"
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
            ] = f"http://{platform.namespace}-docker-registry:5000"
            result["NP_REGISTRY_UPSTREAM_PROJECT"] = "neuro"
        return result

    def create_platform_monitoring_values(
        self, platform: PlatformConfig
    ) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "NP_CLUSTER_NAME": platform.cluster_name,
            "NP_MONITORING_K8S_NS": platform.jobs_namespace,
            "NP_MONITORING_PLATFORM_API_URL": str(platform.api_url),
            "NP_MONITORING_PLATFORM_AUTH_URL": str(platform.auth_url),
            "NP_MONITORING_ES_HOSTS": f"{platform.namespace}-elasticsearch-client:9200",
            "NP_MONITORING_REGISTRY_URL": str(platform.ingress_registry_url),
            "DOCKER_LOGIN_ARTIFACTORY_SECRET_NAME": platform.image_pull_secret_name,
        }
        if platform.on_prem:
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
