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

{{- define "platform.azure.storageAccount.secretName" -}}
{{ .Release.Name }}-azure-storage-account
{{- end -}}

{{- define "platform.jobs.serviceAccountName" -}}
{{ .Release.Name }}-jobs
{{- end -}}

{{- define "platform.jobs.namespace.name" -}}
{{- if .Values.jobs.namespace.name -}}
{{- .Values.jobs.namespace.name | quote -}}
{{- else -}}
{{- printf "%s-jobs" .Release.Namespace | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.idleJobs.priorityClass.name" -}}
{{ .Release.Name }}-idle-job
{{- end -}}

{{- define "platform.storage.platformPvName" -}}
{{ .Release.Name }}-storage
{{- end -}}

{{- define "platform.storage.jobsPvName" -}}
{{ .Release.Name }}-jobs-storage
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