{{- define "platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "platform.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "platform.labels.standard" -}}
app: {{ include "platform.name" . }}
chart: {{ include "platform.chart" . }}
heritage: {{ .Release.Service | quote }}
release: {{ .Release.Name | quote }}
{{- end -}}

{{- define "platform.jobs.namespace.name" -}}
{{- if .Values.jobs.namespace.name -}}
{{- .Values.jobs.namespace.name | quote -}}
{{- else -}}
{{- printf "%s-jobs" .Release.Namespace | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.smb.volumeHandle" -}}
{{- if .path -}}
{{- printf "smb-%s%s" .smb.server .path | replace "." "-" -}}
{{- else -}}
{{- printf "smb-%s" .smb.server | replace "." "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.smb.secretNameSuffix" -}}
{{- if .path -}}
{{- printf "smb-%s%s" .smb.server .path | replace "." "-" -}}
{{- else -}}
{{- printf "smb-%s" .smb.server | replace "." "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.azure.storageAccount.secretNameSuffix" -}}
{{- if . -}}
{{- printf "azure-storage-account%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "azure-storage-account" -}}
{{- end -}}
{{- end -}}

{{- define "platform.storage.platformVolumeNameSuffix" -}}
{{- if . -}}
{{- printf "storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "storage" -}}
{{- end -}}
{{- end -}}

{{- define "platform.storage.jobsVolumeNameSuffix" -}}
{{- if . -}}
{{- printf "jobs-storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "jobs-storage" -}}
{{- end -}}
{{- end -}}

{{- define "platform.storage.claimNameSuffix" -}}
{{- if . -}}
{{- printf "storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "storage" -}}
{{- end -}}
{{- end -}}

{{- define "platform.dockerConfigJson" -}}
{
  "auths": {
    {{ .url | quote }}: {
        "username": {{ .username | quote }},
        "password": {{ .password | quote }},
        "email": {{ .email | quote }},
        "auth": {{ printf "%s:%s" .username .password | b64enc | quote }}
    }
  }
}
{{- end -}}

{{- define "platform.apiUrl" -}}
{{- required "platform.apiUrl is required" .Values.platform.apiUrl -}}
{{- end -}}

{{- define "platform.clusterName" -}}
{{- required "platform.clusterName is required" .Values.platform.clusterName -}}
{{- end -}}

{{- define "platform.clusterDnsName" -}}
{{- required "platform.clusterDnsName is required" .Values.platform.clusterDnsName -}}
{{- end -}}

{{- define "platform.token" -}}
{{- if eq (len .Values.platform.token) 0 -}}
{{- fail "platform.token is required" -}}
{{- end -}}
{{- toYaml .Values.platform.token -}}
{{- end -}}

{{- define "platform.urls" -}}
{{- $apiUrl := include "platform.apiUrl" . -}}
{{- range $key, $value := .Values.platform -}}
{{- if hasSuffix "Url" $key }}
{{ $key }}: {{ default $apiUrl $value }}
{{- end }}
{{- end -}}
{{- end -}}

{{- define "platform.registryUrl" -}}
{{ printf "registry.%s" (include "platform.clusterDnsName" .) }}
{{- end -}}

{{- define "platform.argocd.application" -}}
{{- $root := .root -}}
{{- $project := default "default" $root.Values.argocd.project -}}
{{- $destNs := $root.Release.Namespace -}}
{{- $destServer := default "https://kubernetes.default.svc" $root.Values.argocd.destination.server -}}
{{- $syncWave := default 0 .syncWave | int -}}
{{- $labels := default dict .labels -}}
{{- $annotations := default dict .annotations -}}
{{- $helmDefaultValues := default dict .defaultValues -}}
{{- $helmValues := deepCopy (default dict .values) -}}
{{- $_ := merge $helmValues $helmDefaultValues -}}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ .name | trunc 63 | trimSuffix "-" }}
  labels:
    {{- include "platform.labels.standard" $root | nindent 4 }}
    {{- if gt (len $labels) 0 }}
    {{- range $k, $v := $labels }}
    {{ $k }}: {{ $v | quote }}
    {{- end }}
    {{- end }}
  {{- if or (ne $syncWave 0) (gt (len $annotations) 0) }}
  annotations:
    {{- if ne $syncWave 0 }}
    argocd.argoproj.io/sync-wave: {{ $syncWave | quote }}
    {{- end }}
    {{- range $k, $v := $annotations }}
    {{ $k }}: {{ $v | quote }}
    {{- end }}
  {{- end }}
spec:
  project: {{ $project }}
  destination:
    server: {{ $destServer }}
    namespace: {{ $destNs }}
  source:
    repoURL: {{ required (printf "repoURL for %s application is required" .name) .repoURL }}
    chart: {{ required (printf "chart for %s application is required" .name) .chart }}
    targetRevision: {{ default "latest" .targetRevision | quote }}
    helm:
      {{- with $helmValues }}
      valuesObject:
        {{- toYaml . | nindent 8 }}
      {{- end }}
  {{- with $root.Values.argocd.syncPolicy }}
  syncPolicy:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end -}}
