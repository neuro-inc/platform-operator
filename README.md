# Platform Operator
Platform Operator is a pure k8s component which is responsible for deploying `neu.ro` platform inside k8s cluster.
# Installation
## Platform registration
Before installing platform inside k8s cluster you need to pass registration process in `platform-admin` and `platform-config` services.
## Helm
Helm is required to install platform. Platform operator supports helm 2. Support of helm 3 is unknown.
## Controller
Add `neu.ro` repo (it is anonymous and does not require any credentials, it contains only `platform-operator` helm chart):
```
helm repo add neuro https://neuro.jfrog.io/artifactory/helm-virtual-anonymous
```
Install controller:
```
helm upgrade platform-operator neuro/platform-operator --namespace platform --wait --install
```
## Platform Resource
Install platform resource:
```
kubectl apply -f resource.yaml
```
Example of AWS platform resource:
```
apiVersion: neuromation.io/v1
kind: Platform
metadata:
  name: ${cluster_name}
  namespace: ${platform_namespace}
spec:
  token: ${cluster_token}
  iam:
    aws:
      roles:
        roleArn: arn:aws:iam::771188043543:role/neuro-a44a2ab779525184303d93f9583a3ceb
        s3RoleArn: arn:aws:iam::771188043543:role/s3-a44a2ab779525184303d93f9583a3ceb
  storage:
    nfs:
      path: /
      server: fs-84b34b07.efs.us-east-1.amazonaws.com
  registry:
    aws:
      url: https://771188043543.dkr.ecr.us-east-1.amazonaws.com
  monitoring:
    logs:
      bucket: neuro-job-logs-a44a2ab779525184303d93f9583a3ceb
    metrics:
      bucket: neuro-metrics-a44a2ab779525184303d93f9583a3ceb
```
