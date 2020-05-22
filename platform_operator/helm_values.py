from typing import Any, Dict

from .models import PlatformConfig


class HelmValuesFactory:
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
