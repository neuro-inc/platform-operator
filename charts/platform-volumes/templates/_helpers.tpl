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

{{- define "platform.labels.common" -}}
app: {{ include "platform.name" . }}
chart: {{ include "platform.chart" . }}
heritage: {{ .Release.Service | quote }}
release: {{ .Release.Name | quote }}
{{- end -}}

{{- define "platform.smb.volumeHandle" -}}
{{- if .path -}}
{{- printf "smb-%s%s" .smb.server .path | replace "." "-" -}}
{{- else -}}
{{- printf "smb-%s" .smb.server | replace "." "-" -}}
{{- end -}}
{{- end -}}

{{- define "platform.storage.platformVolumeNameSuffix" -}}
{{- if . -}}
{{- printf "storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "storage" -}}
{{- end -}}
{{- end -}}

{{- define "platform.storage.claimNameSuffix" -}}
{{- if . -}}
{{- printf "storage%s" . | replace "/" "-" -}}
{{- else -}}
{{- printf "storage" -}}
{{- end -}}
{{- end -}}
