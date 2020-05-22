from typing import Any, Dict

from .models import PlatformConfig


class HelmValuesFactory:
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
