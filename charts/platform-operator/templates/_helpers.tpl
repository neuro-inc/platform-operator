{{- define "platformOperator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "platformOperator.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" -}}
{{- end -}}

{{- define "platformOperator.labels.standard" -}}
app: {{ include "platformOperator.name" . }}
chart: {{ include "platformOperator.chart" . }}
heritage: {{ .Release.Service | quote }}
release: {{ .Release.Name | quote }}
{{- end -}}

{{- define "platformOperator.consul.url" -}}
{{- if .Values.consulEnabled -}}
http://consul-server:8500
{{- else -}}
http://platform-consul:8500
{{- end -}}
{{- end -}}

{{- define "platformOperator.postgresqlConfig.fullname" -}}
{{- if .Values.postgresqlConfig.fullnameOverride -}}
{{- .Values.postgresqlConfig.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "postgresql-config" .Values.postgresqlConfig.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.postgresqlConfig.platformApi.migrationsRunnerDsn" -}}
{{- with .Values.postgresqlConfig -}}
{{- $username := .platformApiMigrationsRunnerUsername -}}
{{- $password := .platformApiMigrationsRunnerPassword -}}
{{- $port := toString .port -}}
{{- printf "postgresql://%s:%s@%s:%s/%s" $username $password .host $port .platformApiDatabase -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.postgresqlConfig.platformApi.serviceDsn" -}}
{{- with .Values.postgresqlConfig -}}
{{- $username := .platformApiServiceUsername -}}
{{- $password := .platformApiServicePassword -}}
{{- $port := toString .port -}}
{{- printf "postgresql://%s:%s@%s:%s/%s" $username $password .host $port .platformApiDatabase -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.postgresqlInitScript.fullname" -}}
{{- if .Values.postgresqlInitScript.fullnameOverride -}}
{{- .Values.postgresqlInitScript.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "postgresql-init-script" .Values.postgresqlInitScript.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.platformConfig.fullname" -}}
{{- if .Values.platformConfig.fullnameOverride -}}
{{- .Values.platformConfig.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "platform-config" .Values.platformConfig.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.platformApi.fullname" -}}
{{- if .Values.platformApi.fullnameOverride -}}
{{- .Values.platformApi.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default "platform-api" .Values.platformApi.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "platformOperator.ingress.fallbackHost" -}}
{{- printf "fallback.%s" .Values.ingress.host -}}
{{- end -}}

{{- define "platformOperator.cluster.host" -}}
{{- printf "%s.org.%s" .Values.platformConfig.clusterName .Values.ingress.host -}}
{{- end -}}

{{- define "platformOperator.cluster.url" -}}
{{- $host := include "platformOperator.cluster.host" . -}}
{{- printf "https://%s" $host -}}
{{- end -}}

{{- define "platformOperator.cluster.registryUrl" -}}
{{- $host := include "platformOperator.cluster.host" . -}}
{{- printf "https://registry.%s" $host -}}
{{- end -}}

{{- define "platformOperator.cluster.metricsUrl" -}}
{{- $host := include "platformOperator.cluster.host" . -}}
{{- printf "https://metrics.%s" $host -}}
{{- end -}}
