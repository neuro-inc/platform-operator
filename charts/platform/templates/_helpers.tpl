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
