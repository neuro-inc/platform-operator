{{- define "platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "platform.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "platform.labels.common" -}}
app: {{ include "platform.name" . }}
chart: {{ include "platform.chart" . }}
heritage: {{ .Release.Service | quote }}
release: {{ .Release.Name | quote }}
{{- end -}}

{{- define "platform.storage.claimNameSuffix" -}}
{{- if . -}}
{{- printf "storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "storage" -}}
{{- end -}}
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
{{ printf "https://registry.%s" (include "platform.clusterDnsName" .) }}
{{- end -}}

{{- define "platform.priorityClassName" -}}
{{- $namespace := include "platform.argocd.destination.namespace" . -}}
{{- $priorityClassName := printf "%s-services" $namespace -}}
{{- default $priorityClassName .Values.defaultPriorityClassName -}}
{{- end -}}

{{- define "platform.argocd.destination.namespace" -}}
{{- required "argocd.destination.namespace is required" .Values.argocd.destination.namespace -}}
{{- end -}}

{{- define "platform.argocd.application" -}}
{{- $root := .root -}}
{{- $clusterName := include "platform.clusterName" $root -}}
{{- $namePrefix := ternary "" (printf "%s--" $clusterName) (empty $clusterName) -}}
{{- $nameWithPrefix := printf "%s%s" $namePrefix .name -}}
{{- $name := ternary .name $nameWithPrefix (hasPrefix $namePrefix .name) -}}
{{- $project := default "default" $root.Values.argocd.project -}}
{{- $syncWave := default 0 .syncWave | int -}}
{{- $labels := default dict .labels -}}
{{- $annotations := default dict .annotations -}}
{{- $helmDefaultValues := default dict .defaultValues -}}
{{- $helmValues := deepCopy (default dict .values) -}}
{{- $_ := merge $helmValues $helmDefaultValues -}}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {{ $name | trunc 63 | trimSuffix "-" }}
  labels:
    {{- include "platform.labels.common" $root | nindent 4 }}
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
    {{- toYaml $root.Values.argocd.destination | nindent 4 }}
  source:
    repoURL: {{ required (printf "repoURL for %s application is required" .name) .repoURL }}
    chart: {{ required (printf "chart for %s application is required" .name) .chart }}
    targetRevision: {{ .targetRevision | default "latest" | quote }}
    helm:
      {{- if .releaseName }}
      releaseName: {{ .releaseName }}
      {{- else }}
      releaseName: {{ .name }}
      {{- end }}
      {{- with $helmValues }}
      valuesObject:
        {{- toYaml . | nindent 8 }}
      {{- end }}
  {{- with $root.Values.argocd.syncPolicy }}
  syncPolicy:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end -}}
