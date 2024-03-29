{
  "name": "{{ include "platformOperator.cluster.name" . }}",
  "credentials": {
    "neuro_helm": {
      "url": "oci://ghcr.io/neuro-inc/helm-charts"
    },
    "neuro_registry": {
      "url": "https://ghcr.io/neuro-inc"
    },
    "minio": {
      "username": "{{ .Values.minio.username }}",
      "password": "{{ .Values.minio.password }}"
    }
  },
  "dns": {
    "name": "{{ include "platformOperator.cluster.host" . }}"
  },
  "ingress": {
    "acme_environment": "production"
  },
  "orchestrator": {
    "is_http_ingress_secure": true,
    "job_hostname_template": "{job_id}.jobs.{{ .Values.ingress.host }}",
    "job_internal_hostname_template": "{job_id}.{{ .Values.platformConfig.jobsNamespace | default (print "%s-jobs" .Release.Namespace) }}",
    "job_fallback_hostname": "default.jobs-staging.neu.ro",
    "job_schedule_timeout_s": 180,
    "job_schedule_scale_up_timeout_s": 900,
    "allow_privileged_mode": false,
    "resource_pool_types": {{ .Values.platformConfig.resourcePools | mustToPrettyJson | indent 4 | trim }},
    {{- if .Values.platformConfig.resourcePresets }}
    "resource_presets": [
        {{- with first .Values.platformConfig.resourcePresets -}}
        {{ dict "credits_per_hour" "0" | merge . | mustToPrettyJson | nindent 8 }}
        {{- end -}}
        {{- range rest .Values.platformConfig.resourcePresets -}}
        ,
        {{- dict "credits_per_hour" "0" | merge . | mustToPrettyJson | nindent 8 }}
        {{- end }}
    ],
    {{- else }}
    "resource_presets": [],
    {{- end }}
    "pre_pull_images": []
  },
  "storage": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/storage"
  },
  "blob_storage": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/blob"
  },
  "registry": {
    "url": "{{ include "platformOperator.cluster.registryUrl" . }}"
  },
  "monitoring": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/jobs"
  },
  "secrets": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/secrets"
  },
  "disks": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/disk",
    "storage_limit_per_user_gb": 500
  },
  "buckets": {
    "url": "{{ include "platformOperator.cluster.url" . }}/api/v1/buckets",
    "disable_creation": false
  },
  "metrics": {
    "url": "{{ include "platformOperator.cluster.url" . }}"
  }
}
