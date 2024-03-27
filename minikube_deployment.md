# Standalone deployment of platform in Minikube

## Prerequisites
Before starting you need to have already installed:
- openssl
- minikube 1.22.0 and above
- docker (to be used for minikube if Virtualization support is disabled on your machine)
- helm 3.7.0 and above
- nivida/cuda + nvidia-docker2 (if GPU card is present)

## Self-signed SSL Certificate Generation
### MacOS
```shell
export domain=neu.ro.local
export cluster=default

openssl req \
    -newkey rsa:2048 \
    -x509 \
    -nodes \
    -keyout server.key \
    -new \
    -out server.crt \
    -subj /CN=$domain \
    -reqexts SAN \
    -extensions SAN \
    -config <(cat /System/Library/OpenSSL/openssl.cnf \
        <(printf "[SAN]\nsubjectAltName=DNS:$domain,DNS:$cluster.org.$domain,DNS:*.$cluster.org.$domain,DNS:*.jobs.$cluster.org.$domain,DNS:*.apps.$cluster.org.$domain")) \
    -sha256 \
    -days 365
```

### Ubuntu
```shell
export domain=neu.ro.local
export cluster=default

openssl req \
    -newkey rsa:2048 \
    -x509 \
    -nodes \
    -keyout server.key \
    -new \
    -out server.crt \
    -subj /CN=$domain \
    -reqexts SAN \
    -extensions SAN \
    -config <(cat /usr/lib/ssl/openssl.cnf \
        <(printf "[SAN]\nsubjectAltName=DNS:$domain,DNS:$cluster.org.$domain,DNS:*.$cluster.org.$domain,DNS:*.jobs.$cluster.org.$domain,DNS:*.apps.$cluster.org.$domain")) \
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
Start minikube with CNI enabled. Platform supports Kubernetes versions 1.16.\*-1.21.\*:
```shell
minikube start --cpus="6" --memory="8g" --kubernetes-version="1.20.9" --network-plugin=cni --cni=calico
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

## DNS Configuration
### MacOS
Install Dnsmasq:
```shell
brew install dnsmasq
```
Configure Dnsmasq to resolve your local domain to the Minikube ip:
```shell
minikube_ip=$(minikube ip)
{
    echo "address=/.$domain/$minikube_ip";
    echo "port=53";
} >> $(brew --prefix)/etc/dnsmasq.conf
```
Set your local machine as a DNS resolver:
```shell
sudo tee /etc/resolver/$domain >/dev/null <<EOF
nameserver 127.0.0.1
EOF
```
Start Dnsmasq service:
```shell
sudo brew services start dnsmasq
```

### Ubuntu
Ubuntu 18.04+ comes with systemd-resolve which you need to disable since it binds to port 53 which will conflict with Dnsmasq port. Run the following commands to disable the resolved service:
```shell
sudo systemctl disable systemd-resolved
sudo systemctl stop systemd-resolved
```
Install Dnsmasq:
```shell
sudo apt-get install dnsmasq
```
Configure Dnsmasq to resolve your local domain to the Minikube ip:
```shell
minikube_ip=$(minikube ip)
{
    echo "address=/.$domain/$minikube_ip";
    echo "port=53";
} >> /etc/dnsmasq.conf
```
Set your local machine as a DNS resolver:
```shell
sudo tee /etc/resolver/$domain >/dev/null <<EOF
nameserver 127.0.0.1
EOF
```
Restart Dnsmasq service:
```shell
sudo systemctl restart dnsmasq
```

## Kubernetes Configuration
Create namespace for platform services:
```shell
kubectl create namespace neuro
```
Install nfs-server helm chart:
```shell
helm repo add neuro https://neuro-inc.github.io/helm-charts
helm upgrade nfs-server neuro/nfs-server -f nfs-server-values.yaml -n neuro --install --wait
```
nfs-server-values.yaml file:
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
Install platform-operator helm chart:
```shell
export HELM_EXPERIMENTAL_OCI=1

cat platform-operator-values.yaml | envsubst | helm install \
    platform-operator oci://ghcr.io/neuro-inc/helm-charts/platform-operator \
    -f https://raw.githubusercontent.com/neuro-inc/platform-operator/master/charts/platform-operator/values-standalone.yaml \
    -f - -n=neuro --wait
```
platform-operator-values.yaml file:
```yaml
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
export cert_data=$(cat server.crt | base64)
export cert_key_data=$(cat server.key | base64)
```
Get NFS server service IP address:
```shell
export nfs_server_ip=$(kubectl -n neuro get svc nfs-server -o=jsonpath='{.spec.clusterIP}')
```
Create platform resource:
```shell
cat platform.yaml | envsubst | kubectl apply -f -
```
platform.yaml file:
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
