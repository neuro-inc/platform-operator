# Standalone deployment of platform in Minikube

## Self-signed SSL Certificate Generation
Generate self-signed certificate:
```shell
domain=neu.ro.local
cluster=default

openssl req \
    -newkey rsa:2048 \
    -x509 \
    -nodes \
    -keyout server.key \
    -new \
    -out server.crt \
    -subj /CN=$(domain) \
    -reqexts SAN \
    -extensions SAN \
    -config <(cat /System/Library/OpenSSL/openssl.cnf \
        <(printf "[SAN]\nsubjectAltName=DNS:$domain,DNS:$cluster.org.$domain,DNS:*.$cluster.org.$domain,DNS:*.jobs.$cluster.org.$domain")) \
    -sha256 \
    -days 365
```
Import generated certificate into root certificate store of your OS and trust SSL connections using this certificate.

## Minikube Configuration
Copy generated certificate to minikube's docker daemon certificates folder:
```shell
mkdir -p ~/.minikube/files/etc/docker/certs.d/registry.$cluster.org.$domain
cp server.crt ~/.minikube/files/etc/docker/certs.d/registry.$cluster.org.$domain
```
Start minikube:
```shell
minikube start --vm=true --cpus="6" --memory="8g" --kubernetes-version="1.20.9"
```
Configure minikube node labels:
```shell
kubectl label node minikube platform.neuromation.io/job=true
kubectl label node minikube platform.neuromation.io/nodepool=minikube
```
If you have gpu device installed you need to add additional label:
```shell
kubectl label node minikube platform.neuromation.io/accelerator=$gpu_model
```

## DNS Configuration (MacOS)
Install dnsmasq:
```shell
brew install dnsmasq
```
Configure dnsmasq to resolve your local domain to the Minikube ip:
```shell
minikube_ip=$(minikube ip)
{
    echo "address=/.neu.ro.local/$minikube_ip";
    echo "port=53";
} >> $(brew --prefix)/etc/dnsmasq.conf
```
Set your local machine as a DNS resolver:
```shell
sudo tee /etc/resolver/$domain >/dev/null <<EOF
nameserver 127.0.0.1
EOF
```
Start dnsmasq service:
```shell
sudo brew services start dnsmasq
```

## Kubernetes Configuration
Create namespace for platform services:
```shell
kubectl create namespace neuro
```
Install nfs-server helm chart:
```shell
helm upgrade nfs-server neuro/nfs-server -f values.yaml -n neuro --install --wait
```
nfs-server values file:
```yaml
args: [/exports/neuro]

resources:
  requests:
    cpu: 100m
    memory: 256Mi

persistence:
- accessMode: ReadWriteOnce
  mountPath: /exports/neuro
  size: 100Gi
```
Install platform-operator helm chart (before installation please that chart version is the latest):
```shell
export HELM_EXPERIMENTAL_OCI=1
export version=21.12.29

curl -o values-standalone.yaml https://raw.githubusercontent.com/neuro-inc/platform-operator/v$version/chart/platform-operator/values-standalone.yaml

helm upgrade platform-operator oci://ghcr.io/neuro-inc/helm-charts/platform-operator \
    -f values-standalone.yaml \
    -f values.yaml \
    -n=neuro --install --wait --version $version
```
platform-operator values file:
```yaml
consul:
  server:
    replicas: 1
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 200m
        memory: 256Mi

ingress:
  host: $domain

platformConfig:
  resourcePools:
  - name: minikube
    cpu: 6
    available_cpu: 1
    memory_mb: 8192
    available_memory_mb: 1024

  resourcePresets:
  - name: cpu-small
    cpu: 0.1
    memory_mb: 128
```
Get base64 representation of self-signed certificate which will be used in platform resource file:
```shell
cert_data=$(cat server.crt | base64)
cert_key_data=$(cat server.key | base64)
```
Get NFS server service IP address:
```shell
nfs_server_ip=$(kubectl get svc nfs-server -o json | jq -r .spec.clusterIP)
```
Create platform resource:
```shell
kubectl apply -f platform.yaml
```
Platform resource file:
```yaml
apiVersion: neuromation.io/v1
kind: Platform
metadata:
  name: $cluster
  namespace: neuro
spec:
  kubernetes:
    provider: minikube
    standardStorageClassName: standard
  registry:
    kubernetes:
      persistence:
        storageClassName: standard
        size: 100Gi
  monitoring:
    logs:
      blobStorage:
        bucket: job-logs
  blobStorage:
    kubernetes:
      persistence:
        storageClassName: standard
        size: 100Gi
  disks:
    kubernetes:
      persistence:
        storageClassName: standard
  storages:
  - nfs:
      server: $nfs_server_ip
      path: /exports/neuro
  ingressController:
    replicas: 1
    serviceType: NodePort
    hostPorts:
      http: 80
      https: 443
    ssl:
      certificateData: $cert_data
      certificateKeyData: $cert_key_data
```
Wait until all platform pods are in `Running` state.
